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
from backend.enrollment_routes import router as enrollment_router
from backend.models import User


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

    listed = client.get("/student/enrollments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["course_code"] == "AI-301"

    deleted = client.delete(f"/student/enrollments/{enrollment_id}")
    assert deleted.status_code == 204

    listed_again = client.get("/student/enrollments")
    assert listed_again.status_code == 200
    assert listed_again.json() == []
