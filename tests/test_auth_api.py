from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.api_middleware import register_api_middleware
from backend.account_routes import account_router
from backend.auth_dependencies import require_roles
from backend.auth_routes import router as auth_router
from backend.auth_types import UserRole
from backend.database import Base, get_db
from backend.models import User


def create_test_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = FastAPI()
    register_api_middleware(app)
    register_api_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(account_router)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/admin-only")
    def admin_only(current_user: User = Depends(require_roles(UserRole.ADMIN))):
        return {"user_id": current_user.id}

    client = TestClient(app, raise_server_exceptions=False)
    return client, test_session


def register_student(
    client: TestClient,
    *,
    email: str = "student@example.edu",
    password: str = "Password123",
):
    return client.post(
        "/auth/register",
        json={
            "full_name": "Test Student",
            "email": email,
            "password": password,
        },
    )


def login_student(
    client: TestClient,
    *,
    email: str = "student@example.edu",
    password: str = "Password123",
):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def test_registration_creates_student_only():
    client, _ = create_test_context()
    response = register_student(client, email="STUDENT@EXAMPLE.EDU")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "student@example.edu"
    assert body["role"] == "student"
    assert body["is_active"] is True
    assert "password_hash" not in body


def test_public_registration_cannot_choose_role():
    client, _ = create_test_context()
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Bad Actor",
            "email": "bad@example.edu",
            "password": "Password123",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_duplicate_email_is_rejected():
    client, _ = create_test_context()
    assert register_student(client).status_code == 201
    response = register_student(client)
    assert response.status_code == 409


def test_login_returns_bearer_token():
    client, _ = create_test_context()
    register_student(client)
    response = login_student(client)
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in_seconds"] > 0
    assert body["user"]["role"] == "student"


def test_wrong_password_is_rejected():
    client, _ = create_test_context()
    register_student(client)
    response = login_student(client, password="WrongPassword")
    assert response.status_code == 401


def test_me_requires_authentication():
    client, _ = create_test_context()
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_authenticated_user():
    client, _ = create_test_context()
    register_student(client)
    token = login_student(client).json()["access_token"]
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "student@example.edu"


def test_student_is_forbidden_from_admin_route():
    client, _ = create_test_context()
    register_student(client)
    token = login_student(client).json()["access_token"]
    response = client.get(
        "/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_role_authorization_uses_live_database_role():
    client, test_session = create_test_context()
    register_student(client)
    token = login_student(client).json()["access_token"]

    with test_session() as db:
        user = db.scalar(select(User).where(User.email == "student@example.edu"))
        assert user is not None
        user.role = UserRole.ADMIN.value
        db.commit()

    response = client.get(
        "/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_password_change_revokes_existing_access_tokens():
    client, _ = create_test_context()
    assert register_student(client).status_code == 201
    old_token = login_student(client).json()["access_token"]
    old_headers = {"Authorization": f"Bearer {old_token}"}

    changed = client.post(
        "/account/change-password",
        headers=old_headers,
        json={
            "current_password": "Password123",
            "new_password": "NewPassword123",
        },
    )

    assert changed.status_code == 204
    assert client.get("/auth/me", headers=old_headers).status_code == 401
    new_login = login_student(client, password="NewPassword123")
    assert new_login.status_code == 200
    new_headers = {
        "Authorization": f"Bearer {new_login.json()['access_token']}"
    }
    assert client.get("/auth/me", headers=new_headers).status_code == 200
