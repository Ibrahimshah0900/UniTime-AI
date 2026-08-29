from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.app import app
from backend.auth_dependencies import get_current_user
from backend.auth_security import InvalidAccessTokenError, decode_access_token
from backend.config import AUTH_ALGORITHM, AUTH_SECRET_KEY, DEFAULT_AUTH_SECRET_KEY


PUBLIC_API_ENDPOINTS = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/readiness"),
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
}

COORDINATOR_ADMIN_ENDPOINTS = [
    ("GET", "/students", None),
    ("POST", "/students", {}),
    ("POST", "/students/import", None),
    ("GET", "/students/999999", None),
    ("PATCH", "/students/999999", {}),
    ("POST", "/students/999999/temporary-password", None),
    ("GET", "/course-offerings", None),
    ("POST", "/course-offerings", {}),
    ("PATCH", "/course-offerings/999999", {}),
    ("DELETE", "/course-offerings/999999", None),
    ("GET", "/faculty-teaching-profiles", None),
    ("PUT", "/faculty-teaching-profiles/999999", {}),
    ("GET", "/faculty-availability?faculty_user_id=999999", None),
    ("POST", "/faculty-availability", {}),
    ("DELETE", "/faculty-availability/999999", None),
    ("GET", "/faculty-directory", None),
    ("POST", "/faculty-directory", {}),
    ("GET", "/faculty-assignments", None),
    ("POST", "/faculty-assignments", {}),
    ("DELETE", "/faculty-assignments/999999", None),
    ("POST", "/timetable-generation/preview", {}),
    ("POST", "/timetable-generation/apply", {}),
    ("POST", "/academic-terms", {}),
    ("POST", "/academic-terms/999999/activate", None),
    ("POST", "/academic-terms/999999/archive", None),
    ("GET", "/data-quality", None),
    ("GET", "/resolver-analytics", None),
]

ADMIN_ENDPOINTS = [
    ("GET", "/admin/users", None),
    ("POST", "/admin/users", {}),
    ("PATCH", "/admin/users/999999", {}),
]

FACULTY_ENDPOINTS = [
    ("GET", "/faculty/assignments", None),
    ("GET", "/faculty/timetable", None),
    ("GET", "/faculty/free-slots", None),
    ("GET", "/faculty/availability", None),
    ("POST", "/faculty/availability", {}),
    ("DELETE", "/faculty/availability/999999", None),
]

STUDENT_ENDPOINTS = [
    ("GET", "/student/timetable", None),
    ("GET", "/student/enrollments", None),
    ("POST", "/student/enrollments", {}),
    ("GET", "/student/clash-reports", None),
    ("POST", "/student/clash-reports", {}),
]


def _dependency_calls(dependant):
    if dependant.call is not None:
        yield dependant.call
    for child in dependant.dependencies:
        yield from _dependency_calls(child)


def _fake_user(role: str, *, must_change_password: bool = False):
    return SimpleNamespace(
        id=999999,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
    )


def _request(
    client: TestClient,
    method: str,
    path: str,
    body: dict | None,
):
    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, path, **kwargs)


def test_every_non_public_api_route_has_transitive_authentication_dependency():
    missing: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        dependency_calls = set(_dependency_calls(route.dependant))
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if (method, route.path) in PUBLIC_API_ENDPOINTS:
                continue
            if get_current_user not in dependency_calls:
                missing.append(f"{method} {route.path}")

    assert missing == [], (
        "Non-public API routes without a transitive get_current_user dependency: "
        + ", ".join(missing)
    )


@pytest.mark.parametrize("method,path,body", COORDINATOR_ADMIN_ENDPOINTS)
def test_institutional_management_surface_rejects_anonymous_and_lower_roles(
    method: str,
    path: str,
    body: dict | None,
):
    client = TestClient(app, raise_server_exceptions=False)
    assert _request(client, method, path, body).status_code == 401

    for role in ("student", "faculty"):
        app.dependency_overrides[get_current_user] = (
            lambda role=role: _fake_user(role)
        )
        try:
            assert _request(client, method, path, body).status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
def test_admin_surface_rejects_every_non_admin_role(
    method: str,
    path: str,
    body: dict | None,
):
    client = TestClient(app, raise_server_exceptions=False)
    assert _request(client, method, path, body).status_code == 401

    for role in ("student", "faculty", "coordinator"):
        app.dependency_overrides[get_current_user] = (
            lambda role=role: _fake_user(role)
        )
        try:
            assert _request(client, method, path, body).status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path,body", FACULTY_ENDPOINTS)
def test_faculty_self_service_rejects_non_faculty_roles(
    method: str,
    path: str,
    body: dict | None,
):
    client = TestClient(app, raise_server_exceptions=False)
    assert _request(client, method, path, body).status_code == 401

    for role in ("student", "coordinator", "admin"):
        app.dependency_overrides[get_current_user] = (
            lambda role=role: _fake_user(role)
        )
        try:
            assert _request(client, method, path, body).status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path,body", STUDENT_ENDPOINTS)
def test_student_self_service_rejects_non_student_roles(
    method: str,
    path: str,
    body: dict | None,
):
    client = TestClient(app, raise_server_exceptions=False)
    assert _request(client, method, path, body).status_code == 401

    for role in ("faculty", "coordinator", "admin"):
        app.dependency_overrides[get_current_user] = (
            lambda role=role: _fake_user(role)
        )
        try:
            assert _request(client, method, path, body).status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role,method,path,body",
    [
        ("coordinator", "GET", "/students", None),
        ("admin", "GET", "/admin/users", None),
        ("faculty", "GET", "/faculty/availability", None),
        ("student", "GET", "/student/timetable", None),
    ],
)
def test_temporary_password_accounts_cannot_use_role_gated_features(
    role: str,
    method: str,
    path: str,
    body: dict | None,
):
    client = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides[get_current_user] = lambda: _fake_user(
        role,
        must_change_password=True,
    )
    try:
        response = _request(client, method, path, body)
        assert response.status_code == 403
        assert "temporary password" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.clear()


def _signed_token(payload: dict, *, secret: str = AUTH_SECRET_KEY) -> str:
    return jwt.encode(payload, secret, algorithm=AUTH_ALGORITHM)


def _valid_payload() -> dict:
    now = datetime.now(UTC)
    return {
        "sub": "42",
        "type": "access",
        "ver": 0,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }


def test_access_token_with_wrong_signature_is_rejected():
    token = _signed_token(
        _valid_payload(),
        secret="wrong-signing-secret-with-at-least-32-characters",
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_access_token_missing_version_claim_is_rejected():
    payload = _valid_payload()
    payload.pop("ver")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(_signed_token(payload))


def test_non_access_jwt_type_is_rejected():
    payload = _valid_payload()
    payload["type"] = "refresh"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(_signed_token(payload))


def test_invalid_access_token_subject_is_rejected():
    payload = _valid_payload()
    payload["sub"] = "0"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(_signed_token(payload))


def _production_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "AUTH_SECRET_KEY": "qualification-production-secret-0123456789abcdef",
            "DATABASE_URL": (
                "postgresql+psycopg://unitime:qualification@"
                "db.example.invalid/unitime"
            ),
            "CORS_ORIGINS": "https://app.example.edu",
            "ALLOWED_HOSTS": "api.example.edu",
            "ALLOW_PUBLIC_STUDENT_REGISTRATION": "false",
            "APP_TIMEZONE": "Asia/Karachi",
        }
    )
    env.update(overrides)
    return env


def _import_production_app(**overrides: str) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend.app import app; "
                "print(app.docs_url, app.redoc_url, app.openapi_url)"
            ),
        ],
        cwd=root,
        env=_production_env(**overrides),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )


def test_real_production_startup_rejects_default_auth_secret():
    result = _import_production_app(AUTH_SECRET_KEY=DEFAULT_AUTH_SECRET_KEY)
    assert result.returncode != 0
    assert "Production AUTH_SECRET_KEY" in result.stdout


def test_real_production_startup_rejects_public_registration():
    result = _import_production_app(ALLOW_PUBLIC_STUDENT_REGISTRATION="true")
    assert result.returncode != 0
    assert "Public student registration" in result.stdout


def test_real_production_startup_accepts_hardened_configuration_and_hides_docs():
    result = _import_production_app()
    assert result.returncode == 0, result.stdout
    assert "None None None" in result.stdout
