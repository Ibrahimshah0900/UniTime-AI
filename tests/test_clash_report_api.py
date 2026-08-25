from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.clash_report_routes import review_router, student_router
from backend.database import Base, get_db
from backend.models import StudentEnrollment, StudentProfile, TimetableEntry, User


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
    app.include_router(student_router)
    app.include_router(review_router)

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
        db.flush()
        if role == "student":
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


def seed_student_schedule(Session, student: User) -> tuple[int, int]:
    with Session() as db:
        db.add_all(
            [
                StudentEnrollment(
                    user_id=student.id,
                    course_code="AI-301",
                    section="A",
                    semester="Fall 2026",
                ),
                StudentEnrollment(
                    user_id=student.id,
                    course_code="CS-210",
                    section="B",
                    semester="Fall 2026",
                ),
            ]
        )
        first = TimetableEntry(
            course_code="AI-301",
            section="A,C",
            semester="Fall 2026",
            day="Monday",
            start_time="10:00",
            end_time="11:00",
        )
        second = TimetableEntry(
            course_code="CS-210",
            section="B",
            semester="Fall 2026",
            day="Monday",
            start_time="10:30",
            end_time="11:30",
        )
        db.add_all([first, second])
        db.commit()
        return first.id, second.id


def payload(entry_ids: tuple[int, int]) -> dict:
    return {
        "timetable_entry_ids": list(entry_ids),
        "notes": "Two required classes overlap.",
        "evidence_reference": "portal/schedule/current",
    }


def test_clash_report_routes_require_authentication():
    _, client, _ = create_context()
    assert client.get("/student/clash-reports").status_code == 401
    assert client.get("/clash-reports").status_code == 401
    assert client.get("/clash-reports/1/resolution-candidates").status_code == 401


def test_clash_report_routes_enforce_student_and_reviewer_roles():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")

    app.dependency_overrides[get_current_user] = lambda: coordinator
    assert client.get("/student/clash-reports").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: student
    assert client.get("/clash-reports").status_code == 403
    assert client.get("/clash-reports/1/resolution-candidates").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: faculty
    assert client.get("/clash-reports").status_code == 403
    assert client.get("/clash-reports/1/resolution-candidates").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: coordinator
    assert client.get("/clash-reports").status_code == 200


def test_student_can_submit_list_and_view_own_report():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    entry_ids = seed_student_schedule(Session, student)
    app.dependency_overrides[get_current_user] = lambda: student

    created = client.post("/student/clash-reports", json=payload(entry_ids))
    assert created.status_code == 201
    report_id = created.json()["id"]
    assert created.json()["status"] == "submitted"
    assert len(created.json()["items"]) == 2

    listed = client.get("/student/clash-reports")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["reports"][0]["id"] == report_id

    detail = client.get(f"/student/clash-reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["events"][0]["action"] == "submitted"


def test_student_cannot_view_another_students_report():
    app, client, Session = create_context()
    owner = create_user(Session, "owner@example.edu", "student")
    other = create_user(Session, "other@example.edu", "student")
    entry_ids = seed_student_schedule(Session, owner)

    app.dependency_overrides[get_current_user] = lambda: owner
    report_id = client.post(
        "/student/clash-reports", json=payload(entry_ids)
    ).json()["id"]

    app.dependency_overrides[get_current_user] = lambda: other
    response = client.get(f"/student/clash-reports/{report_id}")
    assert response.status_code == 404


def test_reviewer_can_filter_queue_and_complete_lifecycle():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    entry_ids = seed_student_schedule(Session, student)

    app.dependency_overrides[get_current_user] = lambda: student
    report_id = client.post(
        "/student/clash-reports", json=payload(entry_ids)
    ).json()["id"]

    app.dependency_overrides[get_current_user] = lambda: coordinator
    submitted = client.get("/clash-reports?status=submitted")
    assert submitted.status_code == 200
    assert submitted.json()["total"] == 1

    started = client.patch(
        f"/clash-reports/{report_id}",
        json={"status": "under_review"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "under_review"

    resolved = client.patch(
        f"/clash-reports/{report_id}",
        json={
            "status": "resolved",
            "resolution_note": "The second class was rescheduled.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert len(resolved.json()["events"]) == 3
    assert client.get("/clash-reports?status=submitted").json()["total"] == 0
    assert client.get("/clash-reports?status=resolved").json()["total"] == 1


def test_review_update_requires_resolution_note_and_valid_transition():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    admin = create_user(Session, "admin@example.edu", "admin")
    entry_ids = seed_student_schedule(Session, student)

    app.dependency_overrides[get_current_user] = lambda: student
    report_id = client.post(
        "/student/clash-reports", json=payload(entry_ids)
    ).json()["id"]

    app.dependency_overrides[get_current_user] = lambda: admin
    missing_note = client.patch(
        f"/clash-reports/{report_id}", json={"status": "resolved"}
    )
    assert missing_note.status_code == 422

    direct_resolution = client.patch(
        f"/clash-reports/{report_id}",
        json={"status": "resolved", "resolution_note": "Resolved."},
    )
    assert direct_resolution.status_code == 409


def test_reviewer_gets_deterministic_report_scoped_resolution_candidates():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    entry_ids = seed_student_schedule(Session, student)

    app.dependency_overrides[get_current_user] = lambda: student
    report_id = client.post(
        "/student/clash-reports",
        json=payload(entry_ids),
    ).json()["id"]

    app.dependency_overrides[get_current_user] = lambda: coordinator
    first = client.get(
        f"/clash-reports/{report_id}/resolution-candidates",
        params={
            "target_entry_id": entry_ids[0],
            "limit": 5,
            "include_rejected_limit": 5,
        },
    )
    second = client.get(
        f"/clash-reports/{report_id}/resolution-candidates",
        params={
            "target_entry_id": entry_ids[0],
            "limit": 5,
            "include_rejected_limit": 5,
        },
    )

    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["report_id"] == report_id
    assert body["report_entry_ids"] == list(entry_ids)
    assert body["target_entry_ids"] == [entry_ids[0]]
    assert body["summary"]["generated"] > 0
    assert len(body["candidates"]) <= 5
    assert all(candidate["entry_id"] == entry_ids[0] for candidate in body["candidates"])
    assert all(candidate["status"] != "REJECTED" for candidate in body["candidates"])
    assert "not ML predictions" in body["important_note"]


def test_resolution_candidates_reject_unrelated_target_and_stale_report_state():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    entry_ids = seed_student_schedule(Session, student)
    with Session() as db:
        unrelated = TimetableEntry(
            course_code="MTH-101",
            section="C",
            semester="Fall 2026",
            day="Friday",
            start_time="08:00",
            end_time="09:00",
        )
        db.add(unrelated)
        db.commit()
        unrelated_id = unrelated.id

    app.dependency_overrides[get_current_user] = lambda: student
    report_id = client.post(
        "/student/clash-reports",
        json=payload(entry_ids),
    ).json()["id"]

    app.dependency_overrides[get_current_user] = lambda: coordinator
    unrelated_response = client.get(
        f"/clash-reports/{report_id}/resolution-candidates",
        params={"target_entry_id": unrelated_id},
    )
    assert unrelated_response.status_code == 422

    with Session() as db:
        moved = db.get(TimetableEntry, entry_ids[1])
        moved.day = "Tuesday"
        db.commit()

    stale = client.get(f"/clash-reports/{report_id}/resolution-candidates")
    assert stale.status_code == 409
    assert "no longer overlap" in stale.json()["error"]
