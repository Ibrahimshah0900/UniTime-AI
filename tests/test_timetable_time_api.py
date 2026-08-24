from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.models import (
    Notification,
    StudentEnrollment,
    TimetableChange,
    TimetableEntry,
    User,
)


def create_context():
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
    return TestClient(app), Session


def seed_time_change_context(Session):
    with Session() as db:
        coordinator = User(
            email="coordinator@example.edu",
            full_name="Coordinator User",
            password_hash=hash_password("Password123"),
            role="coordinator",
            is_active=True,
        )
        student = User(
            email="student@example.edu",
            full_name="Student User",
            password_hash=hash_password("Password123"),
            role="student",
            is_active=True,
        )
        db.add_all([coordinator, student])
        db.flush()
        target = TimetableEntry(
            entry_kind="course",
            course_code="AI-301",
            course_name="Artificial Intelligence",
            semester="Fall 2026",
            section="A",
            faculty="Dr. Ada",
            room="CS-301",
            day="Monday",
            start_time="09:00",
            end_time="10:00",
            class_type="lecture",
            source="manual",
        )
        db.add(target)
        db.flush()
        db.add(
            StudentEnrollment(
                user_id=student.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            )
        )
        db.commit()
        return coordinator.id, target.id


def test_safe_manual_time_change_is_audited_notified_and_reversible():
    client, Session = create_context()
    coordinator_id, entry_id = seed_time_change_context(Session)
    with Session() as db:
        coordinator = db.get(User, coordinator_id)
        db.expunge(coordinator)
    app.dependency_overrides[get_current_user] = lambda: coordinator

    try:
        changed = client.patch(
            f"/timetable/{entry_id}/time",
            json={"day": "Tuesday", "start_time": "11:00", "end_time": "12:00"},
        )
        assert changed.status_code == 200
        body = changed.json()
        assert body["entry"]["day"] == "Tuesday"
        assert body["entry"]["start_time"] == "11:00"
        assert body["safety"]["clashes_after"] == 0
        change_id = body["change_id"]

        history = client.get("/changes")
        assert history.status_code == 200
        assert history.json()["changes"][0]["change_type"] == "manual_time_change"
        assert history.json()["changes"][0]["old_day"] == "Monday"
        assert history.json()["changes"][0]["new_day"] == "Tuesday"

        audit = client.get("/audit-trail")
        assert audit.status_code == 200
        assert audit.json()["summary"]["timetable_time_changes"] == 1
        assert audit.json()["audit_trail"][0]["audit_type"] == "timetable_time_change"

        undone = client.post(f"/changes/{change_id}/undo")
        assert undone.status_code == 200
        assert undone.json()["restored_to"]["day"] == "Monday"

        redone = client.post(f"/changes/{change_id}/redo")
        assert redone.status_code == 200
        assert redone.json()["reapplied_to"]["day"] == "Tuesday"

        with Session() as db:
            change = db.get(TimetableChange, change_id)
            entry = db.get(TimetableEntry, entry_id)
            notifications = list(db.scalars(select(Notification)).all())
            assert change is not None and change.undone is False
            assert entry is not None and entry.day == "Tuesday"
            assert len(notifications) == 3
            assert all(item.type == "time_change" for item in notifications)
    finally:
        app.dependency_overrides.clear()


def test_manual_time_change_rejects_an_occupied_faculty_and_room_slot():
    client, Session = create_context()
    coordinator_id, entry_id = seed_time_change_context(Session)
    with Session() as db:
        coordinator = db.get(User, coordinator_id)
        db.add(
            TimetableEntry(
                entry_kind="course",
                course_code="AI-401",
                course_name="Machine Learning",
                semester="Fall 2026",
                section="B",
                faculty="Dr. Ada",
                room="CS-301",
                day="Tuesday",
                start_time="11:00",
                end_time="12:00",
                class_type="lecture",
                source="manual",
            )
        )
        db.commit()
        db.expunge(coordinator)
    app.dependency_overrides[get_current_user] = lambda: coordinator

    try:
        response = client.patch(
            f"/timetable/{entry_id}/time",
            json={"day": "Tuesday", "start_time": "11:00", "end_time": "12:00"},
        )
        assert response.status_code == 409
        with Session() as db:
            entry = db.get(TimetableEntry, entry_id)
            assert entry is not None and entry.day == "Monday"
            assert db.scalar(select(TimetableChange.id)) is None
    finally:
        app.dependency_overrides.clear()


def test_manual_time_change_validates_day_and_time_order():
    client, Session = create_context()
    coordinator_id, entry_id = seed_time_change_context(Session)
    with Session() as db:
        coordinator = db.get(User, coordinator_id)
        db.expunge(coordinator)
    app.dependency_overrides[get_current_user] = lambda: coordinator

    try:
        invalid_day = client.patch(
            f"/timetable/{entry_id}/time",
            json={"day": "Someday", "start_time": "11:00", "end_time": "12:00"},
        )
        invalid_order = client.patch(
            f"/timetable/{entry_id}/time",
            json={"day": "Tuesday", "start_time": "12:00", "end_time": "11:00"},
        )
        assert invalid_day.status_code == 422
        assert invalid_order.status_code == 422
    finally:
        app.dependency_overrides.clear()
