from __future__ import annotations

from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from openpyxl import Workbook

from backend.account_routes import account_router
from backend.api_errors import register_api_error_handlers
from backend.auth_routes import router as auth_router
from backend.auth_security import hash_password, verify_password
from backend.database import Base, get_db
from backend.enrollment_routes import router as enrollment_router
from backend.faculty_routes import directory_router as faculty_directory_router
from backend.models import StudentProfile, User
from backend.student_identity_routes import (
    account_router as student_profile_router,
    management_router as student_management_router,
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
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(student_profile_router)
    app.include_router(student_management_router)
    app.include_router(enrollment_router)
    app.include_router(faculty_directory_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), Session


def create_operator(Session, *, role: str = "coordinator") -> tuple[User, str]:
    password = "OperatorPassword123"
    with Session() as db:
        user = User(
            email=f"{role}@example.edu",
            full_name=f"Test {role.title()}",
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user, password


def login(client: TestClient, identifier: str, password: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def provision_payload(**changes) -> dict:
    payload = {
        "registration_number": "FA23-BAI-042",
        "full_name": "Ayesha Student",
        "department": "Computer Science",
        "program": "BS Artificial Intelligence",
        "batch": "Fall 2023",
        "current_semester": 6,
        "section": "A",
    }
    payload.update(changes)
    return payload


def coordinator_headers(client: TestClient, Session) -> dict[str, str]:
    _, password = create_operator(Session)
    token = login(client, "coordinator@example.edu", password)["access_token"]
    return authorization(token)


def test_provisioned_registration_number_login_and_first_login_gates():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)

    created = client.post("/students", headers=headers, json=provision_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    temporary_password = body["temporary_password"]
    student = body["student"]
    assert student["institutional_email"] is None
    assert student["registration_number"] == "FA23-BAI-042"
    assert student["is_verified"] is True
    assert student["must_change_password"] is True
    assert student["onboarding_completed"] is False

    with Session() as db:
        persisted = db.get(User, student["user_id"])
        assert persisted.email is None
        assert persisted.password_hash != temporary_password
        assert verify_password(temporary_password, persisted.password_hash)

    first_login = login(client, "fa23-bai-042", temporary_password)
    first_headers = authorization(first_login["access_token"])
    assert first_login["user"]["student_profile"]["registration_number"] == "FA23-BAI-042"
    assert client.get("/student/enrollments", headers=first_headers).status_code == 403

    changed = client.post(
        "/account/change-password",
        headers=first_headers,
        json={
            "current_password": temporary_password,
            "new_password": "PermanentPassword123",
        },
    )
    assert changed.status_code == 204
    assert client.get("/auth/me", headers=first_headers).status_code == 401

    ready_login = login(client, "FA23-BAI-042", "PermanentPassword123")
    ready_headers = authorization(ready_login["access_token"])
    assert client.get("/student/enrollments", headers=ready_headers).status_code == 403
    completed = client.patch(
        "/account/student-profile",
        headers=ready_headers,
        json={"preferred_name": "Ayesha", "complete_onboarding": True},
    )
    assert completed.status_code == 200
    assert completed.json()["preferred_name"] == "Ayesha"
    assert completed.json()["onboarding_completed"] is True
    assert client.get("/student/enrollments", headers=ready_headers).status_code == 200


def test_student_cannot_edit_institutional_identity_but_operator_can():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    created = client.post(
        "/students",
        headers=headers,
        json=provision_payload(
            email="student@example.edu",
            temporary_password="TemporaryPassword123",
        ),
    ).json()
    user_id = created["student"]["user_id"]
    student_login = login(client, "student@example.edu", "TemporaryPassword123")
    student_headers = authorization(student_login["access_token"])

    blocked = client.patch(
        "/account/profile",
        headers=student_headers,
        json={"full_name": "Spoofed Identity"},
    )
    assert blocked.status_code == 403

    updated = client.patch(
        f"/students/{user_id}",
        headers=headers,
        json={
            "registration_number": "FA23-BAI-043",
            "full_name": "Corrected Student Name",
            "current_semester": 7,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["registration_number"] == "FA23-BAI-043"
    assert updated.json()["full_name"] == "Corrected Student Name"
    assert updated.json()["current_semester"] == 7


def test_duplicate_and_malformed_student_identity_is_rejected():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    first = client.post(
        "/students",
        headers=headers,
        json=provision_payload(email="official@example.edu"),
    )
    assert first.status_code == 201
    assert client.post(
        "/students",
        headers=headers,
        json=provision_payload(email="other@example.edu"),
    ).status_code == 409
    assert client.post(
        "/students",
        headers=headers,
        json=provision_payload(
            registration_number="FA23-BAI-999",
            email="official@example.edu",
        ),
    ).status_code == 409
    malformed = client.post(
        "/students",
        headers=headers,
        json=provision_payload(registration_number="not valid!", current_semester=0),
    )
    assert malformed.status_code == 422


def test_public_registration_can_be_disabled_without_affecting_provisioning(monkeypatch):
    client, Session = create_context()
    import backend.auth_routes as auth_routes

    monkeypatch.setattr(
        auth_routes.config,
        "ALLOW_PUBLIC_STUDENT_REGISTRATION",
        False,
    )
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Unprovisioned Student",
            "email": "unprovisioned@example.edu",
            "password": "Password123",
        },
    )
    assert response.status_code == 403
    with Session() as db:
        assert db.scalar(select(func.count(User.id))) == 0


def test_unverified_inactive_and_deactivated_students_cannot_operate():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    created = client.post(
        "/students",
        headers=headers,
        json=provision_payload(
            is_verified=False,
            temporary_password="TemporaryPassword123",
        ),
    ).json()
    user_id = created["student"]["user_id"]
    token = login(client, "FA23-BAI-042", "TemporaryPassword123")["access_token"]
    temp_headers = authorization(token)
    assert client.post(
        "/account/change-password",
        headers=temp_headers,
        json={
            "current_password": "TemporaryPassword123",
            "new_password": "PermanentPassword123",
        },
    ).status_code == 204
    student_headers = authorization(
        login(client, "FA23-BAI-042", "PermanentPassword123")["access_token"]
    )
    assert client.patch(
        "/account/student-profile",
        headers=student_headers,
        json={"complete_onboarding": True},
    ).status_code == 200
    assert client.get("/student/enrollments", headers=student_headers).status_code == 403

    verified = client.patch(
        f"/students/{user_id}", headers=headers, json={"is_verified": True}
    )
    assert verified.status_code == 200
    assert client.get("/student/enrollments", headers=student_headers).status_code == 200

    deactivated = client.patch(
        f"/students/{user_id}", headers=headers, json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert client.get("/auth/me", headers=student_headers).status_code == 401
    assert client.post(
        "/auth/login",
        json={"identifier": "FA23-BAI-042", "password": "PermanentPassword123"},
    ).status_code == 401


def test_roster_import_preview_is_transactional_and_apply_returns_credentials():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    invalid_csv = (
        "registration_no,full_name,email,department,program,batch,semester,section\n"
        "FA23-BAI-001,First Student,,Computing,BS AI,2023,3,A\n"
        "bad identity!,Second Student,invalid,Computing,BS AI,2023,99,B\n"
    ).encode()
    preview = client.post(
        "/students/import?dry_run=true",
        headers=headers,
        files={"file": ("roster.csv", BytesIO(invalid_csv), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_apply"] is False
    assert preview.json()["invalid"] == 1
    assert preview.json()["applied"] is False
    with Session() as db:
        assert db.scalar(select(func.count(StudentProfile.user_id))) == 0

    valid_csv = (
        "registration_no,full_name,email,department,program,batch,semester,section\n"
        "FA23-BAI-001,First Student,,Computing,BS AI,2023,3,A\n"
        "FA23-BCS-002,Second Student,second@example.edu,Computing,BS CS,2023,3,B\n"
    ).encode()
    applied = client.post(
        "/students/import?dry_run=false",
        headers=headers,
        files={"file": ("roster.csv", BytesIO(valid_csv), "text/csv")},
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["applied"] is True
    assert body["would_create"] == 2
    assert len(body["credentials"]) == 2
    first_credential = next(
        item for item in body["credentials"] if item["registration_number"] == "FA23-BAI-001"
    )
    assert login(
        client,
        "FA23-BAI-001",
        first_credential["temporary_password"],
    )["user"]["must_change_password"] is True

    duplicate_preview = client.post(
        "/students/import?dry_run=true",
        headers=headers,
        files={"file": ("roster.csv", BytesIO(valid_csv), "text/csv")},
    )
    assert duplicate_preview.json()["duplicates"] == 2
    assert duplicate_preview.json()["would_create"] == 0


def test_roster_duplicate_rows_abort_all_writes_and_safe_update_preserves_access_state():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    duplicate_csv = (
        "registration_no,full_name,department,program,batch,semester,section\n"
        "FA23-BAI-010,First Student,Computing,BS AI,2023,3,A\n"
        "FA23-BAI-010,Duplicate Student,Computing,BS AI,2023,3,B\n"
    ).encode()
    response = client.post(
        "/students/import?dry_run=false",
        headers=headers,
        files={"file": ("roster.csv", BytesIO(duplicate_csv), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["applied"] is False
    with Session() as db:
        assert db.scalar(select(func.count(StudentProfile.user_id))) == 0

    created = client.post(
        "/students",
        headers=headers,
        json=provision_payload(
            registration_number="FA23-BAI-010",
            full_name="Old Name",
            email="preserved@example.edu",
            is_verified=False,
            is_active=False,
        ),
    ).json()["student"]
    update_csv = (
        "registration_no,full_name,department,program,batch,semester,section\n"
        "FA23-BAI-010,Updated Name,Engineering,BS AI,2023,4,C\n"
    ).encode()
    updated = client.post(
        "/students/import?dry_run=false&update_existing=true",
        headers=headers,
        files={"file": ("roster.csv", BytesIO(update_csv), "text/csv")},
    )
    assert updated.status_code == 200
    assert updated.json()["would_update"] == 1
    identity = client.get(f"/students/{created['user_id']}", headers=headers).json()
    assert identity["full_name"] == "Updated Name"
    assert identity["department"] == "Engineering"
    assert identity["current_semester"] == 4
    assert identity["institutional_email"] == "preserved@example.edu"
    assert identity["is_verified"] is False
    assert identity["is_active"] is False


def test_coordinator_can_provision_faculty_with_mandatory_password_change():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    created = client.post(
        "/faculty-directory",
        headers=headers,
        json={"full_name": "Faculty Member", "email": "faculty@example.edu"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["faculty"]["role"] == "faculty"
    assert body["faculty"]["must_change_password"] is True
    faculty_login = login(client, "faculty@example.edu", body["temporary_password"])
    faculty_headers = authorization(faculty_login["access_token"])
    assert client.get("/faculty-directory", headers=faculty_headers).status_code == 403


def test_xlsx_roster_preview_uses_the_same_validation_contract():
    client, Session = create_context()
    headers = coordinator_headers(client, Session)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        [
            "registration_no",
            "full_name",
            "department",
            "program",
            "batch",
            "semester",
            "section",
        ]
    )
    worksheet.append(
        ["FA24-BAI-001", "XLSX Student", "Computing", "BS AI", "2024", 2, "A"]
    )
    content = BytesIO()
    workbook.save(content)
    content.seek(0)

    response = client.post(
        "/students/import?dry_run=true",
        headers=headers,
        files={
            "file": (
                "roster.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["can_apply"] is True
    assert response.json()["would_create"] == 1
    assert response.json()["invalid"] == 0
