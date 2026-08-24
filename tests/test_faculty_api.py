from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.faculty_routes import directory_router, faculty_router, management_router
from backend.models import TimetableEntry, User


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
    app.include_router(faculty_router)
    app.include_router(directory_router)
    app.include_router(management_router)

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


def assignment_payload(faculty_user_id: int) -> dict:
    return {
        "faculty_user_id": faculty_user_id,
        "course_code": "AI-301",
        "section": "A",
        "semester": "Fall 2026",
    }


def test_faculty_routes_require_authentication():
    _, client, _ = create_context()
    assert client.get("/faculty/assignments").status_code == 401
    assert client.get("/faculty/timetable").status_code == 401
    assert client.get("/faculty-assignments").status_code == 401
    assert client.get("/faculty-directory").status_code == 401


def test_faculty_and_management_routes_enforce_roles():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")

    app.dependency_overrides[get_current_user] = lambda: student
    assert client.get("/faculty/timetable").status_code == 403
    assert client.get("/faculty-assignments").status_code == 403
    assert client.get("/faculty-directory").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: faculty
    assert client.get("/faculty/timetable").status_code == 200
    assert client.get("/faculty-assignments").status_code == 403
    assert client.get("/faculty-directory").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: coordinator
    assert client.get("/faculty/timetable").status_code == 403
    assert client.get("/faculty-assignments").status_code == 200
    assert client.get("/faculty-directory").status_code == 200


def test_coordinator_can_search_minimal_active_faculty_directory():
    app, client, Session = create_context()
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    visible = create_user(Session, "ada.faculty@example.edu", "faculty")
    create_user(Session, "other.faculty@example.edu", "faculty")
    create_user(Session, "student@example.edu", "student")
    with Session() as db:
        db.add(
            User(
                email="inactive.faculty@example.edu",
                full_name="Inactive Faculty",
                password_hash=hash_password("Password123"),
                role="faculty",
                is_active=False,
            )
        )
        db.commit()

    app.dependency_overrides[get_current_user] = lambda: coordinator
    response = client.get("/faculty-directory?search=ada&limit=10")

    assert response.status_code == 200
    assert response.json() == {
        "faculty": [
            {
                "id": visible.id,
                "full_name": visible.full_name,
                "email": visible.email,
            }
        ],
        "total": 1,
        "offset": 0,
        "limit": 10,
    }


def test_coordinator_assigns_class_and_faculty_reads_own_timetable():
    app, client, Session = create_context()
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    with Session() as db:
        entry = TimetableEntry(
            course_code="AI-301",
            section="A,C",
            semester=None,
            day="Monday",
            start_time="10:00",
            end_time="11:00",
        )
        db.add(entry)
        db.commit()

    app.dependency_overrides[get_current_user] = lambda: coordinator
    created = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id),
    )
    assert created.status_code == 201
    assignment_id = created.json()["id"]

    managed = client.get(f"/faculty-assignments?faculty_user_id={faculty.id}")
    assert managed.status_code == 200
    assert len(managed.json()) == 1

    app.dependency_overrides[get_current_user] = lambda: faculty
    assignments = client.get("/faculty/assignments")
    timetable = client.get("/faculty/timetable")
    assert assignments.status_code == 200
    assert assignments.json()[0]["course_code"] == "AI-301"
    assert timetable.status_code == 200
    assert [entry["course_code"] for entry in timetable.json()] == ["AI-301"]

    app.dependency_overrides[get_current_user] = lambda: coordinator
    deleted = client.delete(f"/faculty-assignments/{assignment_id}")
    assert deleted.status_code == 204


def test_student_cannot_create_faculty_assignment():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    app.dependency_overrides[get_current_user] = lambda: student

    response = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id),
    )

    assert response.status_code == 403
