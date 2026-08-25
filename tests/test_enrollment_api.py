from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.enrollment_conflict_graph import build_enrollment_conflict_analysis
from backend.enrollment_routes import router as enrollment_router
from backend.enrollment_service import get_student_timetable
from backend.models import StudentProfile, TimetableEntry, User


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
    app.include_router(enrollment_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def create_student(Session):
    with Session() as db:
        user = User(
            email="student@example.edu",
            full_name="Test Student",
            password_hash=hash_password("Password123"),
            role="student",
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            StudentProfile(
                user_id=user.id,
                registration_number=f"TEST-{user.id:06d}",
                department="Computing",
                program="BS AI",
                batch="2026",
                current_semester=3,
                section="A",
                is_verified=True,
                onboarding_completed=True,
            )
        )
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def payload():
    return {
        "course_code": "AI-301",
        "section": "A",
        "semester": "Fall 2026",
    }


def test_enrollment_api_requires_authentication():
    app, client, _ = create_context()
    response = client.get("/student/enrollments")
    assert response.status_code == 401


def test_non_student_roles_are_forbidden():
    for role in ("faculty", "coordinator", "admin"):
        app, client, _ = create_context()
        app.dependency_overrides[get_current_user] = lambda role=role: SimpleNamespace(id=1, role=role, is_active=True)
        response = client.get("/student/enrollments")
        assert response.status_code == 403


def test_student_can_create_list_and_delete_enrollment():
    app, client, Session = create_context()
    student = create_student(Session)
    app.dependency_overrides[get_current_user] = lambda: student

    created = client.post("/student/enrollments", json=payload())
    assert created.status_code == 201
    enrollment_id = created.json()["id"]
    assert created.json()["conflict_validation"]["has_conflicts"] is False
    assert created.json()["conflict_validation"]["mapped_timetable_entry_ids"] == []

    listed = client.get("/student/enrollments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["course_code"] == "AI-301"

    deleted = client.delete(f"/student/enrollments/{enrollment_id}")
    assert deleted.status_code == 204

    listed_again = client.get("/student/enrollments")
    assert listed_again.status_code == 200
    assert listed_again.json() == []


def test_add_validation_reports_live_conflict_and_unverified_alternate_without_auto_move():
    app, client, Session = create_context()
    student = create_student(Session)
    app.dependency_overrides[get_current_user] = lambda: student
    with Session() as db:
        db.add_all(
            [
                TimetableEntry(
                    course_code="AI-301",
                    course_name="Artificial Intelligence",
                    section="A",
                    semester="Fall 2026",
                    day="Tuesday",
                    start_time="10:00",
                    end_time="11:30",
                ),
                TimetableEntry(
                    course_code="CS-210",
                    course_name="Algorithms",
                    section="A",
                    semester="Fall 2026",
                    day="Tuesday",
                    start_time="10:30",
                    end_time="11:30",
                ),
                TimetableEntry(
                    course_code="CS-210",
                    course_name="Algorithms",
                    section="B",
                    semester="Fall 2026",
                    day="Friday",
                    start_time="09:00",
                    end_time="10:00",
                ),
            ]
        )
        db.commit()

    first = client.post(
        "/student/enrollments",
        json={
            "course_code": "AI-301",
            "section": "A",
            "semester": "Fall 2026",
        },
    )
    assert first.status_code == 201
    assert first.json()["conflict_validation"]["has_conflicts"] is False

    proposed = {
        "course_code": "CS-210",
        "section": "A",
        "semester": "Fall 2026",
    }
    preview = client.post("/student/enrollments/validate", json=proposed)
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["has_conflicts"] is True
    assert len(preview_body["conflicts"]) == 1
    assert preview_body["conflicts"][0]["proposed_class"]["course_code"] == "CS-210"
    assert preview_body["conflicts"][0]["conflicts_with"]["course_code"] == "AI-301"
    assert preview_body["conflicts"][0]["overlap_start"] == "10:30"
    assert preview_body["conflicts"][0]["overlap_end"] == "11:30"
    section_b = next(
        item for item in preview_body["alternate_sections"] if item["section"] == "B"
    )
    assert section_b["conflict_free"] is True
    assert section_b["validation_status"] == "timetable_only_unverified"
    assert any("capacity" in note.lower() for note in section_b["limitations"])
    assert len(client.get("/student/enrollments").json()) == 1

    created = client.post("/student/enrollments", json=proposed)
    assert created.status_code == 201
    assert created.json()["section"] == "A"
    assert created.json()["conflict_validation"] == preview_body
    cs_enrollment_id = created.json()["id"]

    with Session() as db:
        personal = get_student_timetable(db, student.id)
        analysis = build_enrollment_conflict_analysis(db, personal)
        assert {entry.course_code for entry in personal} == {"AI-301", "CS-210"}
        assert analysis["coverage"]["enrollment_backed_edges"] == 1

    assert client.delete(
        f"/student/enrollments/{cs_enrollment_id}"
    ).status_code == 204
    with Session() as db:
        personal_after_drop = get_student_timetable(db, student.id)
        analysis_after_drop = build_enrollment_conflict_analysis(
            db, personal_after_drop
        )
        assert [entry.course_code for entry in personal_after_drop] == ["AI-301"]
        assert analysis_after_drop["coverage"]["enrollment_backed_edges"] == 0
