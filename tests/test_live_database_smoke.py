from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.app import app
from backend.auth_service import create_privileged_account
from backend.auth_types import UserRole
from backend.database import SessionLocal, engine
from backend.models import FacultyClassAssignment, StudentEnrollment, TimetableEntry, User


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATABASE_TESTS") != "1",
    reason="Live database smoke tests are enabled explicitly in disposable CI databases.",
)


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_live_postgresql_role_flow():
    assert engine.dialect.name == "postgresql"

    namespace = uuid4().hex[:12]
    password = "LiveSmokePassword123"
    admin_email = f"admin-{namespace}@example.edu"
    coordinator_email = f"coordinator-{namespace}@example.edu"
    faculty_email = f"faculty-{namespace}@example.edu"
    student_email = f"student-{namespace}@example.edu"
    course_code = f"TST-{namespace[:6]}"

    with SessionLocal() as db:
        create_privileged_account(
            db,
            email=admin_email,
            full_name="Smoke Admin",
            password=password,
            role=UserRole.ADMIN,
        )

    try:
        with TestClient(app) as client:
            admin_token = login(client, admin_email, password)
            admin_headers = authorization(admin_token)

            coordinator = client.post(
                "/admin/users",
                headers=admin_headers,
                json={
                    "full_name": "Smoke Coordinator",
                    "email": coordinator_email,
                    "password": password,
                    "role": "coordinator",
                },
            )
            faculty = client.post(
                "/admin/users",
                headers=admin_headers,
                json={
                    "full_name": "Smoke Faculty",
                    "email": faculty_email,
                    "password": password,
                    "role": "faculty",
                },
            )
            student = client.post(
                "/auth/register",
                json={
                    "full_name": "Smoke Student",
                    "email": student_email,
                    "password": password,
                },
            )
            assert coordinator.status_code == 201
            assert faculty.status_code == 201
            assert student.status_code == 201

            coordinator_token = login(client, coordinator_email, password)
            coordinator_headers = authorization(coordinator_token)
            timetable = client.post(
                "/timetable",
                headers=coordinator_headers,
                json={
                    "course_code": course_code,
                    "course_name": "Database Smoke Test",
                    "semester": "Fall 2026",
                    "section": "A",
                    "faculty": "Smoke Faculty",
                    "room": "T-101",
                    "day": "Monday",
                    "start_time": "09:00",
                    "end_time": "10:00",
                },
            )
            assert timetable.status_code == 201

            assignment = client.post(
                "/faculty-assignments",
                headers=coordinator_headers,
                json={
                    "faculty_user_id": faculty.json()["id"],
                    "course_code": course_code,
                    "section": "A",
                    "semester": "Fall 2026",
                },
            )
            assert assignment.status_code == 201

            student_token = login(client, student_email, password)
            student_headers = authorization(student_token)
            enrollment = client.post(
                "/student/enrollments",
                headers=student_headers,
                json={
                    "course_code": course_code,
                    "section": "A",
                    "semester": "Fall 2026",
                },
            )
            assert enrollment.status_code == 201
            assert len(client.get("/student/timetable", headers=student_headers).json()) == 1

            faculty_token = login(client, faculty_email, password)
            faculty_headers = authorization(faculty_token)
            assert len(client.get("/faculty/timetable", headers=faculty_headers).json()) == 1
            assert client.get("/dashboard", headers=admin_headers).status_code == 200
            assert client.get("/ready").status_code == 200
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(FacultyClassAssignment).where(
                    FacultyClassAssignment.course_code == course_code
                )
            )
            db.execute(
                delete(StudentEnrollment).where(
                    StudentEnrollment.course_code == course_code
                )
            )
            db.execute(
                delete(TimetableEntry).where(TimetableEntry.course_code == course_code)
            )
            db.execute(
                delete(User).where(
                    User.email.in_(
                        (
                            admin_email,
                            coordinator_email,
                            faculty_email,
                            student_email,
                        )
                    )
                )
            )
            db.commit()
