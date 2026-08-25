from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.enrollment_schemas import EnrollmentCreate
from backend.enrollment_service import (
    create_student_enrollment,
    delete_student_enrollment,
    get_student_timetable,
    list_student_enrollments,
)
from backend.models import (
    AcademicTerm,
    LearningEvent,
    StudentEnrollment,
    TimetableEntry,
    User,
)
from backend.term_routes import router as term_router
from backend.term_schemas import AcademicTermCreate
from backend.term_service import (
    activate_academic_term,
    archive_academic_term,
    create_academic_term,
    get_active_term,
    resolve_term_for_write,
)


def create_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = FastAPI()
    register_api_error_handlers(app)
    app.include_router(term_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def create_user(Session, *, email: str, role: str) -> User:
    with Session() as db:
        user = User(
            email=email,
            full_name=email.split("@")[0].title(),
            password_hash=hash_password("Password123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def term_payload(code: str = "FALL-2026") -> dict:
    return {
        "code": code,
        "name": "Fall 2026",
        "starts_on": "2026-08-24",
        "ends_on": "2026-12-18",
    }


def test_term_routes_require_authentication_and_management_role():
    app, client, Session = create_context()
    student = create_user(Session, email="student@example.edu", role="student")

    assert client.get("/academic-terms").status_code == 401
    assert client.get("/academic-terms/current").status_code == 401
    assert client.post("/academic-terms", json=term_payload()).status_code == 401

    app.dependency_overrides[get_current_user] = lambda: student
    current = client.get("/academic-terms/current")
    assert current.status_code == 200
    assert current.json()["code"] == "LEGACY-IMPORTED"
    assert client.post("/academic-terms", json=term_payload()).status_code == 403
    assert client.post("/academic-terms/1/archive").status_code == 403


def test_coordinator_runs_strict_term_lifecycle_without_overwriting_history():
    app, client, Session = create_context()
    coordinator = create_user(
        Session,
        email="coordinator@example.edu",
        role="coordinator",
    )
    app.dependency_overrides[get_current_user] = lambda: coordinator

    initial = client.get("/academic-terms")
    assert initial.status_code == 200
    legacy_id = initial.json()["active_term_id"]

    with Session() as db:
        db.add(
            TimetableEntry(
                term_id=legacy_id,
                course_code="LEG-101",
                section="A",
                day="Monday",
                start_time="09:00",
                end_time="10:00",
            )
        )
        db.commit()

    created = client.post("/academic-terms", json=term_payload())
    assert created.status_code == 201
    planning_id = created.json()["id"]
    assert created.json()["status"] == "planning"

    still_active = client.post(f"/academic-terms/{planning_id}/activate")
    assert still_active.status_code == 409
    assert "Archive the current active term" in still_active.json()["error"]

    archived = client.post(f"/academic-terms/{legacy_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    activated = client.post(f"/academic-terms/{planning_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    with Session() as db:
        assert db.scalar(select(func.count(TimetableEntry.id))) == 1
        historical = db.scalar(
            select(TimetableEntry).where(TimetableEntry.course_code == "LEG-101")
        )
        assert historical is not None
        assert historical.term_id == legacy_id
        archived_event = db.scalar(
            select(LearningEvent).where(
                LearningEvent.event_type == "term_archived"
            )
        )
        assert archived_event is not None
        assert archived_event.actor_role == "coordinator"
        assert archived_event.term_id == legacy_id
        assert get_active_term(db).id == planning_id
        try:
            resolve_term_for_write(db, legacy_id)
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "Archived academic terms are read-only."
        else:
            raise AssertionError("Archived term unexpectedly allowed a write.")

    duplicate = client.post("/academic-terms", json=term_payload())
    assert duplicate.status_code == 409
    assert client.post(f"/academic-terms/{legacy_id}/archive").status_code == 409


def test_term_validation_rejects_invalid_dates_and_codes():
    app, client, Session = create_context()
    coordinator = create_user(
        Session,
        email="coordinator@example.edu",
        role="coordinator",
    )
    app.dependency_overrides[get_current_user] = lambda: coordinator

    backwards = term_payload()
    backwards["starts_on"] = "2026-12-19"
    assert client.post("/academic-terms", json=backwards).status_code == 422

    invalid_code = term_payload("Fall 2026!")
    assert client.post("/academic-terms", json=invalid_code).status_code == 422


def test_enrollments_and_personal_timetable_are_isolated_by_active_term():
    _, _, Session = create_context()
    student = create_user(Session, email="student@example.edu", role="student")
    coordinator = create_user(
        Session,
        email="coordinator@example.edu",
        role="coordinator",
    )

    with Session() as db:
        legacy = get_active_term(db)
        db.add(
            TimetableEntry(
                term_id=legacy.id,
                course_code="AI-301",
                section="A",
                day="Monday",
                start_time="09:00",
                end_time="10:00",
            )
        )
        db.commit()
        old_enrollment = create_student_enrollment(
            db,
            user_id=student.id,
            request=EnrollmentCreate(
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            ),
        )
        next_term = create_academic_term(
            db,
            actor_user_id=coordinator.id,
            request=AcademicTermCreate(
                code="SPRING-2027",
                name="Spring 2027",
            ),
        )
        archive_academic_term(db, term_id=legacy.id)
        activate_academic_term(db, term_id=next_term.id)
        db.add(
            TimetableEntry(
                term_id=next_term.id,
                course_code="AI-301",
                section="A",
                day="Tuesday",
                start_time="13:00",
                end_time="14:00",
            )
        )
        db.commit()
        new_enrollment = create_student_enrollment(
            db,
            user_id=student.id,
            request=EnrollmentCreate(
                course_code="AI-301",
                section="A",
                semester="Spring 2027",
            ),
        )

        assert new_enrollment.term_id == next_term.id
        assert [item.id for item in list_student_enrollments(db, student.id)] == [
            new_enrollment.id
        ]
        assert [entry.day for entry in get_student_timetable(db, student.id)] == [
            "Tuesday"
        ]
        assert db.scalar(select(func.count(StudentEnrollment.id))) == 2

        try:
            delete_student_enrollment(
                db,
                user_id=student.id,
                enrollment_id=old_enrollment.id,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Archived enrollment was unexpectedly deleted.")
