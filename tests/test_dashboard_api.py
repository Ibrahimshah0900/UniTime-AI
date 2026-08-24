from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.dashboard_routes import router
from backend.database import Base, get_db
from backend.models import (
    FacultyClassAssignment,
    Notification,
    StudentClashReport,
    StudentEnrollment,
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
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def create_user(Session, email: str, role: str) -> User:
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


def test_dashboard_requires_authentication():
    _, client, _ = create_context()
    assert client.get("/dashboard").status_code == 401


def test_student_dashboard_contains_student_workflow_counts():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    with Session() as db:
        db.add(StudentEnrollment(user_id=student.id, course_code="AI-301", section="A", semester="Fall 2026"))
        db.add(StudentClashReport(student_user_id=student.id, status="submitted"))
        db.add(Notification(user_id=student.id, type="schedule_change", title="Changed", message="Changed"))
        db.commit()
    app.dependency_overrides[get_current_user] = lambda: student

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.json()["role"] == "student"
    assert response.json()["data"]["enrollment_count"] == 1
    assert response.json()["data"]["clash_reports_by_status"] == {"submitted": 1}
    assert response.json()["data"]["unread_notifications"] == 1


def test_faculty_dashboard_contains_assignment_counts():
    app, client, Session = create_context()
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    with Session() as db:
        db.add(FacultyClassAssignment(faculty_user_id=faculty.id, course_code="AI-301", section="A", semester="Fall 2026", created_by_user_id=coordinator.id))
        db.commit()
    app.dependency_overrides[get_current_user] = lambda: faculty

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.json()["role"] == "faculty"
    assert response.json()["data"]["assignment_count"] == 1


def test_coordinator_and_admin_dashboards_expose_operational_counts():
    app, client, Session = create_context()
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    admin = create_user(Session, "admin@example.edu", "admin")
    student = create_user(Session, "student@example.edu", "student")
    with Session() as db:
        db.add(TimetableEntry(course_code="AI-301", day="Monday", start_time="10:00", end_time="11:00", room="R1"))
        db.add(StudentClashReport(student_user_id=student.id, status="under_review"))
        db.commit()

    app.dependency_overrides[get_current_user] = lambda: coordinator
    coordinator_response = client.get("/dashboard")
    assert coordinator_response.status_code == 200
    assert coordinator_response.json()["data"]["pending_clash_reports"] == 1
    assert coordinator_response.json()["data"]["timetable_entry_count"] == 1

    app.dependency_overrides[get_current_user] = lambda: admin
    admin_response = client.get("/dashboard")
    assert admin_response.status_code == 200
    assert admin_response.json()["data"]["users_by_role"]["admin"] == 1
    assert admin_response.json()["data"]["active_users"] == 3
