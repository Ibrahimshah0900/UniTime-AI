from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.data_quality_routes import router
from backend.database import Base, get_db
from backend.models import (
    AcademicTerm,
    FacultyClassAssignment,
    StudentEnrollment,
    StudentProfile,
    TimetableEntry,
    User,
)


def create_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(AcademicTerm(id=1, code="TEST-TERM", name="Test Term", status="active"))
        db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session, engine


def create_user(Session, *, email: str | None, role: str, active: bool = True) -> User:
    with Session() as db:
        user = User(
            email=email,
            full_name=f"{role.title()} User",
            password_hash=hash_password("Password123"),
            role=role,
            is_active=active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_data_quality_requires_coordinator_or_admin():
    app, client, Session, engine = create_context()
    try:
        assert client.get("/data-quality").status_code == 401
        student = create_user(Session, email="student@example.edu", role="student")
        app.dependency_overrides[get_current_user] = lambda: student
        assert client.get("/data-quality").status_code == 403
    finally:
        engine.dispose()


def test_data_quality_reports_actionable_term_scoped_findings_without_exposing_values():
    app, client, Session, engine = create_context()
    try:
        coordinator = create_user(Session, email="coordinator@example.edu", role="coordinator")
        student = create_user(Session, email="bad-email", role="student")
        inactive_faculty = create_user(Session, email="faculty@example.edu", role="faculty", active=False)
        with Session() as db:
            db.add(
                StudentProfile(
                    user_id=student.id,
                    registration_number="TEST-001",
                    department="Computing",
                    program="BS AI",
                    batch="2026",
                    current_semester=3,
                    section="A",
                    is_verified=True,
                    onboarding_completed=True,
                )
            )
            db.add(
                StudentEnrollment(
                    term_id=1,
                    user_id=student.id,
                    course_code="NO-OFFERING",
                    section="A",
                    semester="Semester 3",
                )
            )
            duplicate = dict(
                term_id=1,
                course_code="AI-301",
                course_name="Artificial Intelligence",
                semester="Semester 3",
                section="A",
                faculty=None,
                room=None,
                day="Funday",
                start_time="12:30",
                end_time="11:30",
                class_type="lecture",
            )
            db.add_all([TimetableEntry(**duplicate), TimetableEntry(**duplicate)])
            db.add(
                FacultyClassAssignment(
                    term_id=1,
                    faculty_user_id=inactive_faculty.id,
                    course_code="AI-999",
                    section="A",
                    semester="Semester 3",
                    created_by_user_id=coordinator.id,
                )
            )
            db.commit()
            before = {
                "users": db.scalar(select(func.count(User.id))),
                "entries": db.scalar(select(func.count(TimetableEntry.id))),
                "enrollments": db.scalar(select(func.count(StudentEnrollment.id))),
            }

        app.dependency_overrides[get_current_user] = lambda: coordinator
        response = client.get("/data-quality")
        assert response.status_code == 200
        payload = response.json()
        codes = {issue["issue_code"] for issue in payload["issues"]}
        assert {
            "MALFORMED_USER_EMAIL",
            "INVALID_TIMETABLE_DAY",
            "IMPOSSIBLE_TIMETABLE_TIME_RANGE",
            "MISSING_TIMETABLE_FACULTY",
            "MISSING_TIMETABLE_ROOM",
            "DUPLICATE_TIMETABLE_ENTRY",
            "UNKNOWN_COURSE_OFFERING",
            "INACTIVE_OR_INVALID_FACULTY_ASSIGNMENT",
            "FACULTY_ASSIGNMENT_WITHOUT_TIMETABLE_OFFERING",
        }.issubset(codes)
        serialized = response.text
        assert "bad-email" not in serialized
        assert "TEST-001" not in serialized
        assert payload["summary"]["total"] == len(payload["issues"])

        with Session() as db:
            after = {
                "users": db.scalar(select(func.count(User.id))),
                "entries": db.scalar(select(func.count(TimetableEntry.id))),
                "enrollments": db.scalar(select(func.count(StudentEnrollment.id))),
            }
        assert before == after
    finally:
        engine.dispose()


def test_data_quality_clean_minimal_term_has_no_false_capacity_findings():
    app, client, Session, engine = create_context()
    try:
        coordinator = create_user(Session, email="coordinator@example.edu", role="coordinator")
        faculty = create_user(Session, email="faculty@example.edu", role="faculty")
        with Session() as db:
            db.add(
                TimetableEntry(
                    term_id=1,
                    course_code="AI-301",
                    semester="Semester 3",
                    section="A",
                    faculty=faculty.full_name,
                    room="R-101",
                    day="Monday",
                    start_time="10:00",
                    end_time="11:30",
                )
            )
            db.add(
                FacultyClassAssignment(
                    term_id=1,
                    faculty_user_id=faculty.id,
                    course_code="AI-301",
                    section="A",
                    semester="Semester 3",
                    created_by_user_id=coordinator.id,
                )
            )
            db.commit()
        app.dependency_overrides[get_current_user] = lambda: coordinator
        payload = client.get("/data-quality").json()
        assert all("CAPACITY" not in issue["issue_code"] for issue in payload["issues"])
        assert payload["summary"]["critical"] == 0
    finally:
        engine.dispose()
