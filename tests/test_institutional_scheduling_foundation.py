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
from backend.faculty_routes import management_router
from backend.institutional_scheduling_routes import (
    course_offering_router,
    faculty_availability_management_router,
    faculty_profile_router,
    faculty_self_availability_router,
)
from backend.models import AcademicTerm, User


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
    app.include_router(course_offering_router)
    app.include_router(faculty_profile_router)
    app.include_router(faculty_availability_management_router)
    app.include_router(faculty_self_availability_router)
    app.include_router(management_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def create_user(Session, email: str, role: str, *, active: bool = True) -> User:
    with Session() as db:
        user = User(
            email=email,
            full_name=email.split("@")[0].replace(".", " ").title(),
            password_hash=hash_password("Password123"),
            role=role,
            is_active=active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def create_terms(Session) -> tuple[int, int]:
    with Session() as db:
        active = AcademicTerm(code="FALL-2026", name="Fall 2026", status="active")
        planning = AcademicTerm(code="SPRING-2027", name="Spring 2027", status="planning")
        db.add_all([active, planning])
        db.commit()
        db.refresh(active)
        db.refresh(planning)
        return active.id, planning.id


def offering_payload(term_id: int, code: str, semester: int = 5, *, class_type: str = "lecture") -> dict:
    return {
        "term_id": term_id,
        "course_code": code,
        "course_name": f"{code} Course",
        "semester": semester,
        "section": "A",
        "class_type": class_type,
        "duration_minutes": 60 if class_type == "lecture" else 120,
        "room": "R-101" if class_type == "lecture" else "LAB-1",
    }


def assignment_payload(faculty_user_id: int, term_id: int, code: str, semester: int = 5) -> dict:
    return {
        "faculty_user_id": faculty_user_id,
        "term_id": term_id,
        "course_code": code,
        "section": "A",
        "semester": str(semester),
    }


def test_course_offerings_are_planning_term_coordinator_admin_workflow():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    student = create_user(Session, "student@example.edu", "student")

    app.dependency_overrides[get_current_user] = lambda: student
    assert client.get(f"/course-offerings?term_id={planning_id}").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: coordinator
    created = client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "AI-501"),
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["course_code"] == "AI-501"
    assert payload["semester"] == 5
    assert payload["class_type"] == "lecture"

    duplicate = client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "ai-501"),
    )
    assert duplicate.status_code == 409

    listed = client.get(f"/course-offerings?term_id={planning_id}")
    assert listed.status_code == 200
    assert [item["course_code"] for item in listed.json()] == ["AI-501"]

    updated = client.patch(
        f"/course-offerings/{payload['id']}",
        json={"course_name": "Advanced Artificial Intelligence", "duration_minutes": 90},
    )
    assert updated.status_code == 200
    assert updated.json()["course_name"] == "Advanced Artificial Intelligence"
    assert updated.json()["duration_minutes"] == 90

    deleted = client.delete(f"/course-offerings/{payload['id']}")
    assert deleted.status_code == 204


def test_course_offering_validation_and_archived_term_write_protection():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    app.dependency_overrides[get_current_user] = lambda: coordinator

    bad_semester = offering_payload(planning_id, "BAD-900")
    bad_semester["semester"] = 9
    assert client.post("/course-offerings", json=bad_semester).status_code == 422

    with Session() as db:
        planning = db.get(AcademicTerm, planning_id)
        planning.status = "archived"
        db.commit()

    response = client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "AI-501"),
    )
    assert response.status_code == 409


def test_lecturer_limit_is_four_distinct_subjects_and_same_course_components_count_once():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    faculty = create_user(Session, "lecturer@example.edu", "faculty")
    app.dependency_overrides[get_current_user] = lambda: coordinator

    profile = client.put(
        f"/faculty-teaching-profiles/{faculty.id}?term_id={planning_id}",
        json={"designation": "lecturer"},
    )
    assert profile.status_code == 200
    assert profile.json()["maximum_subjects"] == 4

    # Both components represent one subject allocation.
    assert client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "AI-501", class_type="lecture"),
    ).status_code == 201
    assert client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "AI-501", class_type="lab"),
    ).status_code == 201

    for code in ("AI-501", "DB-502", "SE-503", "NW-504", "OS-505"):
        if code != "AI-501":
            assert client.post(
                "/course-offerings",
                json=offering_payload(planning_id, code),
            ).status_code == 201

    for code in ("AI-501", "DB-502", "SE-503", "NW-504"):
        created = client.post(
            "/faculty-assignments",
            json=assignment_payload(faculty.id, planning_id, code),
        )
        assert created.status_code == 201, created.text

    workload = client.get(
        f"/faculty-teaching-profiles?term_id={planning_id}&faculty_user_id={faculty.id}"
    )
    assert workload.status_code == 200
    assert workload.json()[0]["distinct_subjects_assigned"] == 4
    assert workload.json()[0]["remaining_capacity"] == 0

    fifth = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id, planning_id, "OS-505"),
    )
    assert fifth.status_code == 409
    assert "limited to 4" in fifth.json()["error"]


def test_assistant_professor_limit_is_two_subjects():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    faculty = create_user(Session, "ap@example.edu", "faculty")
    app.dependency_overrides[get_current_user] = lambda: coordinator

    assert client.put(
        f"/faculty-teaching-profiles/{faculty.id}?term_id={planning_id}",
        json={"designation": "assistant_professor"},
    ).status_code == 200

    for code in ("AI-501", "DB-502", "SE-503"):
        assert client.post(
            "/course-offerings",
            json=offering_payload(planning_id, code),
        ).status_code == 201

    for code in ("AI-501", "DB-502"):
        assert client.post(
            "/faculty-assignments",
            json=assignment_payload(faculty.id, planning_id, code),
        ).status_code == 201

    third = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id, planning_id, "SE-503"),
    )
    assert third.status_code == 409
    assert "limited to 2" in third.json()["error"]


def test_planning_assignment_requires_profile_and_matching_course_offering():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    faculty = create_user(Session, "faculty@example.edu", "faculty")
    app.dependency_overrides[get_current_user] = lambda: coordinator

    missing_profile = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id, planning_id, "AI-501"),
    )
    assert missing_profile.status_code == 409

    assert client.put(
        f"/faculty-teaching-profiles/{faculty.id}?term_id={planning_id}",
        json={"designation": "lecturer"},
    ).status_code == 200

    missing_offering = client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id, planning_id, "AI-501"),
    )
    assert missing_offering.status_code == 409

    assert client.post(
        "/course-offerings",
        json=offering_payload(planning_id, "AI-501"),
    ).status_code == 201
    assert client.post(
        "/faculty-assignments",
        json=assignment_payload(faculty.id, planning_id, "AI-501"),
    ).status_code == 201


def test_true_faculty_availability_is_distinct_from_timetable_free_slots():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
    faculty = create_user(Session, "faculty@example.edu", "faculty")

    app.dependency_overrides[get_current_user] = lambda: faculty
    created = client.post(
        "/faculty/availability",
        json={
            "term_id": planning_id,
            "day": "Monday",
            "start_time": "09:00",
            "end_time": "13:00",
        },
    )
    assert created.status_code == 201
    window_id = created.json()["id"]

    own = client.get(f"/faculty/availability?term_id={planning_id}")
    assert own.status_code == 200
    assert [(item["day"], item["start_time"], item["end_time"]) for item in own.json()] == [
        ("Monday", "09:00", "13:00")
    ]

    overlap = client.post(
        "/faculty/availability",
        json={
            "term_id": planning_id,
            "day": "Monday",
            "start_time": "12:00",
            "end_time": "15:00",
        },
    )
    assert overlap.status_code == 409

    invalid = client.post(
        "/faculty/availability",
        json={
            "term_id": planning_id,
            "day": "Monday",
            "start_time": "07:00",
            "end_time": "09:00",
        },
    )
    assert invalid.status_code == 422

    app.dependency_overrides[get_current_user] = lambda: coordinator
    managed = client.get(
        f"/faculty-availability?faculty_user_id={faculty.id}&term_id={planning_id}"
    )
    assert managed.status_code == 200
    assert managed.json()[0]["id"] == window_id
    assert client.delete(f"/faculty-availability/{window_id}").status_code == 204


def test_faculty_cannot_delete_another_faculty_availability():
    app, client, Session = create_context()
    _, planning_id = create_terms(Session)
    first = create_user(Session, "first@example.edu", "faculty")
    second = create_user(Session, "second@example.edu", "faculty")

    app.dependency_overrides[get_current_user] = lambda: first
    created = client.post(
        "/faculty/availability",
        json={
            "term_id": planning_id,
            "day": "Tuesday",
            "start_time": "10:00",
            "end_time": "12:00",
        },
    )
    assert created.status_code == 201

    app.dependency_overrides[get_current_user] = lambda: second
    assert client.delete(
        f"/faculty/availability/{created.json()['id']}"
    ).status_code == 404
