from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.auth_service import create_privileged_account
from backend.auth_types import UserRole
from backend.database import Base, get_db


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, identifier: str, password: str = "Password123") -> str:
    response = client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_complete_backend_role_journey_with_real_tokens():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        with Session() as db:
            create_privileged_account(
                db,
                email="admin@example.edu",
                full_name="Admin User",
                password="Password123",
                role=UserRole.ADMIN,
            )

        admin_token = login(client, "admin@example.edu")
        admin_headers = auth_header(admin_token)

        coordinator = client.post(
            "/admin/users",
            headers=admin_headers,
            json={
                "full_name": "Coordinator User",
                "email": "coordinator@example.edu",
                "password": "Password123",
                "role": "coordinator",
            },
        )
        faculty = client.post(
            "/admin/users",
            headers=admin_headers,
            json={
                "full_name": "Faculty User",
                "email": "faculty@example.edu",
                "password": "Password123",
                "role": "faculty",
            },
        )
        assert coordinator.status_code == 201
        assert faculty.status_code == 201

        registration = client.post(
            "/students",
            headers=admin_headers,
            json={
                "registration_number": "FA23-BAI-042",
                "full_name": "Student User",
                "email": "student@example.edu",
                "department": "Computer Science",
                "program": "BS Artificial Intelligence",
                "batch": "Fall 2023",
                "current_semester": 6,
                "section": "A",
                "temporary_password": "TemporaryPassword123",
            },
        )
        assert registration.status_code == 201
        temporary_token = login(
            client,
            "student@example.edu",
            "TemporaryPassword123",
        )
        temporary_headers = auth_header(temporary_token)
        assert client.post(
            "/account/change-password",
            headers=temporary_headers,
            json={
                "current_password": "TemporaryPassword123",
                "new_password": "Password123",
            },
        ).status_code == 204
        student_token = login(client, "FA23-BAI-042")
        student_headers = auth_header(student_token)
        assert client.patch(
            "/account/student-profile",
            headers=student_headers,
            json={"complete_onboarding": True},
        ).status_code == 200

        first = client.post(
            "/timetable",
            headers=admin_headers,
            json={
                "course_code": "AI-301",
                "course_name": "Artificial Intelligence",
                "semester": "Fall 2026",
                "section": "A,C",
                "faculty": "DrAI",
                "room": "R1",
                "day": "Monday",
                "start_time": "10:00",
                "end_time": "11:00",
            },
        )
        second = client.post(
            "/timetable",
            headers=admin_headers,
            json={
                "course_code": "CS-210",
                "course_name": "Algorithms",
                "semester": "Fall 2026",
                "section": "B",
                "faculty": "DrCS",
                "room": "R2",
                "day": "Monday",
                "start_time": "10:30",
                "end_time": "11:30",
            },
        )
        assert first.status_code == 201
        assert second.status_code == 201

        for enrollment in (
            {"course_code": "AI-301", "section": "A", "semester": "Fall 2026"},
            {"course_code": "CS-210", "section": "B", "semester": "Fall 2026"},
        ):
            assert client.post(
                "/student/enrollments",
                headers=student_headers,
                json=enrollment,
            ).status_code == 201
        timetable = client.get("/student/timetable", headers=student_headers)
        assert timetable.status_code == 200
        assert len(timetable.json()) == 2

        report = client.post(
            "/student/clash-reports",
            headers=student_headers,
            json={
                "timetable_entry_ids": [first.json()["id"], second.json()["id"]],
                "notes": "Both required classes overlap.",
            },
        )
        assert report.status_code == 201
        report_id = report.json()["id"]

        coordinator_token = login(client, "coordinator@example.edu")
        coordinator_headers = auth_header(coordinator_token)
        queue = client.get(
            "/clash-reports?status=submitted",
            headers=coordinator_headers,
        )
        assert queue.status_code == 200
        assert queue.json()["total"] == 1
        assert client.patch(
            f"/clash-reports/{report_id}",
            headers=coordinator_headers,
            json={"status": "under_review"},
        ).status_code == 200
        assert client.patch(
            f"/clash-reports/{report_id}",
            headers=coordinator_headers,
            json={
                "status": "resolved",
                "resolution_note": "Coordinator rescheduled the conflicting class.",
            },
        ).status_code == 200

        assignment = client.post(
            "/faculty-assignments",
            headers=coordinator_headers,
            json={
                "faculty_user_id": faculty.json()["id"],
                "course_code": "AI-301",
                "section": "A",
                "semester": "Fall 2026",
            },
        )
        assert assignment.status_code == 201

        faculty_token = login(client, "faculty@example.edu")
        faculty_headers = auth_header(faculty_token)
        faculty_timetable = client.get("/faculty/timetable", headers=faculty_headers)
        assert faculty_timetable.status_code == 200
        assert [entry["course_code"] for entry in faculty_timetable.json()] == ["AI-301"]

        notifications = client.get("/notifications", headers=student_headers)
        assert notifications.status_code == 200
        assert notifications.json()["total"] == 2
        assert {
            item["payload"]["status"] for item in notifications.json()["notifications"]
        } == {"under_review", "resolved"}

        for headers, expected_role in (
            (student_headers, "student"),
            (faculty_headers, "faculty"),
            (coordinator_headers, "coordinator"),
            (admin_headers, "admin"),
        ):
            dashboard = client.get("/dashboard", headers=headers)
            assert dashboard.status_code == 200
            assert dashboard.json()["role"] == expected_role

        assert client.get("/optimizer/plan", headers=student_headers).status_code == 403
        assert client.get("/optimizer/plan", headers=faculty_headers).status_code == 403
        assert client.get("/optimizer/plan", headers=coordinator_headers).status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
