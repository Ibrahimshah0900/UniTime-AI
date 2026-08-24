from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.database import Base
from backend.models import (
    FacultyClassAssignment,
    StudentEnrollment,
    TimetableEntry,
    User,
)
from backend.notification_schemas import NotificationPreferenceUpdate
from backend.notification_service import (
    add_notification,
    add_schedule_change_notifications,
    get_notification_preferences,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    process_due_notifications,
    update_notification_preferences,
)


def create_test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_user(db, email: str, role: str) -> User:
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
    return user


def test_notification_preferences_have_defaults_and_can_be_updated():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu", "student")
        defaults = get_notification_preferences(db, student.id)
        assert defaults["class_reminder_minutes"] == 15
        assert defaults["daily_summary_enabled"] is False

        updated = update_notification_preferences(
            db,
            user_id=student.id,
            request=NotificationPreferenceUpdate(
                class_reminder_minutes=30,
                daily_summary_enabled=True,
                daily_summary_time="06:30",
                schedule_change_enabled=False,
                clash_report_updates_enabled=True,
            ),
        )
        assert updated["class_reminder_minutes"] == 30
        assert updated["daily_summary_time"] == "06:30"
        assert updated["schedule_change_enabled"] is False


def test_notification_list_and_read_state_are_user_scoped():
    Session = create_test_session()
    with Session() as db:
        owner = create_user(db, "owner@example.edu", "student")
        other = create_user(db, "other@example.edu", "student")
        notification = add_notification(
            db,
            user_id=owner.id,
            notification_type="schedule_change",
            title="Schedule changed",
            message="Your class moved.",
            payload={"timetable_entry_id": 10},
            dedup_key="change:10",
        )
        db.commit()
        db.refresh(notification)

        listed = list_notifications(db, user_id=owner.id)
        assert listed["total"] == 1
        assert listed["unread_count"] == 1
        assert listed["notifications"][0]["payload"] == {"timetable_entry_id": 10}

        with pytest.raises(HTTPException) as exc_info:
            mark_notification_read(
                db,
                user_id=other.id,
                notification_id=notification.id,
            )
        assert exc_info.value.status_code == 404

        read = mark_notification_read(
            db,
            user_id=owner.id,
            notification_id=notification.id,
        )
        assert read["read_at"] is not None
        assert list_notifications(db, user_id=owner.id)["unread_count"] == 0


def test_mark_all_notifications_read_updates_only_the_current_user():
    Session = create_test_session()
    with Session() as db:
        owner = create_user(db, "owner@example.edu", "student")
        other = create_user(db, "other@example.edu", "student")
        for index in range(2):
            add_notification(
                db,
                user_id=owner.id,
                notification_type="schedule_change",
                title="Changed",
                message="Changed",
                dedup_key=f"owner:{index}",
            )
        add_notification(
            db,
            user_id=other.id,
            notification_type="schedule_change",
            title="Changed",
            message="Changed",
            dedup_key="other:1",
        )
        db.commit()

        assert mark_all_notifications_read(db, user_id=owner.id) == 2
        assert list_notifications(db, user_id=owner.id)["unread_count"] == 0
        assert list_notifications(db, user_id=other.id)["unread_count"] == 1


def test_due_processor_creates_deduplicated_reminder_and_daily_summary():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu", "student")
        db.add(
            StudentEnrollment(
                user_id=student.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            )
        )
        db.add(
            TimetableEntry(
                course_code="AI-301",
                section="A,C",
                semester=None,
                room="Lab 1",
                day="Monday",
                start_time="10:00",
                end_time="11:00",
            )
        )
        db.commit()
        update_notification_preferences(
            db,
            user_id=student.id,
            request=NotificationPreferenceUpdate(
                class_reminder_minutes=15,
                daily_summary_enabled=True,
                daily_summary_time="07:00",
            ),
        )
        now = datetime(2026, 8, 24, 9, 50, tzinfo=ZoneInfo("Asia/Karachi"))

        first = process_due_notifications(db, now=now)
        second = process_due_notifications(db, now=now)

        assert first["reminders_created"] == 1
        assert first["summaries_created"] == 1
        assert second["reminders_created"] == 0
        assert second["summaries_created"] == 0
        assert list_notifications(db, user_id=student.id)["total"] == 2


def test_schedule_change_notifies_matching_students_and_faculty():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu", "student")
        faculty = create_user(db, "faculty@example.edu", "faculty")
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        db.add(
            StudentEnrollment(
                user_id=student.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            )
        )
        db.add(
            FacultyClassAssignment(
                faculty_user_id=faculty.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
                created_by_user_id=coordinator.id,
            )
        )
        entry = TimetableEntry(
            course_code="AI-301",
            section="A,C",
            semester=None,
            room="R2",
            day="Monday",
            start_time="10:00",
            end_time="11:00",
        )
        db.add(entry)
        db.commit()

        created = add_schedule_change_notifications(
            db,
            entry=entry,
            notification_type="room_change",
            title="Room changed",
            message="Room changed to R2.",
            event_key="room:1",
        )
        db.commit()

        assert created == 2
        assert list_notifications(db, user_id=student.id)["total"] == 1
        assert list_notifications(db, user_id=faculty.id)["total"] == 1


def test_schedule_change_preference_can_disable_delivery():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu", "student")
        db.add(
            StudentEnrollment(
                user_id=student.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            )
        )
        entry = TimetableEntry(
            course_code="AI-301",
            section="A",
            semester="Fall 2026",
            day="Monday",
            start_time="10:00",
            end_time="11:00",
        )
        db.add(entry)
        db.commit()
        update_notification_preferences(
            db,
            user_id=student.id,
            request=NotificationPreferenceUpdate(schedule_change_enabled=False),
        )

        assert add_schedule_change_notifications(
            db,
            entry=entry,
            notification_type="time_change",
            title="Changed",
            message="Changed",
            event_key="time:1",
        ) == 0
