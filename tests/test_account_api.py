from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.account_routes import account_router, admin_router
from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password, verify_password
from backend.database import Base, get_db
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
    app.include_router(account_router)
    app.include_router(admin_router)

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


def test_account_and_admin_routes_require_authentication():
    _, client, _ = create_context()
    assert client.patch("/account/profile", json={"full_name": "New Name"}).status_code == 401
    assert client.get("/admin/users").status_code == 401


def test_user_can_update_profile_and_change_password():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    app.dependency_overrides[get_current_user] = lambda: student

    profile = client.patch("/account/profile", json={"full_name": "  Updated   Student "})
    assert profile.status_code == 200
    assert profile.json()["full_name"] == "Updated Student"

    wrong = client.post(
        "/account/change-password",
        json={"current_password": "WrongPassword", "new_password": "NewPassword123"},
    )
    assert wrong.status_code == 400

    changed = client.post(
        "/account/change-password",
        json={"current_password": "Password123", "new_password": "NewPassword123"},
    )
    assert changed.status_code == 204
    with Session() as db:
        persisted = db.get(User, student.id)
        assert verify_password("NewPassword123", persisted.password_hash)


def test_only_admin_can_manage_users():
    app, client, Session = create_context()
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    admin = create_user(Session, "admin@example.edu", "admin")

    app.dependency_overrides[get_current_user] = lambda: coordinator
    assert client.get("/admin/users").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: admin
    created = client.post(
        "/admin/users",
        json={
            "full_name": "Faculty User",
            "email": "FACULTY@example.edu",
            "password": "Password123",
            "role": "faculty",
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "faculty@example.edu"
    assert created.json()["role"] == "faculty"

    listed = client.get("/admin/users?role=faculty&search=faculty")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/admin/users/{created.json()['id']}",
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_admin_cannot_deactivate_or_demote_self():
    app, client, Session = create_context()
    admin = create_user(Session, "admin@example.edu", "admin")
    app.dependency_overrides[get_current_user] = lambda: admin

    assert client.patch(
        f"/admin/users/{admin.id}", json={"is_active": False}
    ).status_code == 409
    assert client.patch(
        f"/admin/users/{admin.id}", json={"role": "coordinator"}
    ).status_code == 409
