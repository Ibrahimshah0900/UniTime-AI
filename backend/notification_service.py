from __future__ import annotations

import json
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import APP_TIMEZONE
from backend.enrollment_service import get_student_timetable
from backend.faculty_service import get_faculty_timetable
from backend.models import (
    FacultyClassAssignment,
    Notification,
    NotificationPreference,
    StudentEnrollment,
    TimetableEntry,
    User,
)
from backend.term_service import get_active_term
from backend.notification_schemas import NotificationPreferenceUpdate
from backend.schedule_matching import section_matches, semester_matches


DEFAULT_PREFERENCES = {
    "class_reminder_minutes": 15,
    "daily_summary_enabled": False,
    "daily_summary_time": "07:00",
    "schedule_change_enabled": True,
    "clash_report_updates_enabled": True,
}


def _timezone() -> ZoneInfo:
    try:
        return ZoneInfo(APP_TIMEZONE)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"APP_TIMEZONE is not a valid IANA timezone: {APP_TIMEZONE}") from exc


def _preference_values(preference: NotificationPreference | None) -> dict:
    if preference is None:
        return dict(DEFAULT_PREFERENCES)
    return {
        "class_reminder_minutes": preference.class_reminder_minutes,
        "daily_summary_enabled": preference.daily_summary_enabled,
        "daily_summary_time": preference.daily_summary_time,
        "schedule_change_enabled": preference.schedule_change_enabled,
        "clash_report_updates_enabled": preference.clash_report_updates_enabled,
    }


def get_notification_preferences(db: Session, user_id: int) -> dict:
    preference = db.get(NotificationPreference, user_id)
    return {
        "user_id": user_id,
        **_preference_values(preference),
        "updated_at": preference.updated_at if preference is not None else None,
    }


def update_notification_preferences(
    db: Session,
    *,
    user_id: int,
    request: NotificationPreferenceUpdate,
) -> dict:
    preference = db.get(NotificationPreference, user_id)
    if preference is None:
        preference = NotificationPreference(user_id=user_id)
        db.add(preference)
    for field, value in request.model_dump().items():
        setattr(preference, field, value)
    try:
        db.commit()
        db.refresh(preference)
    except Exception:
        db.rollback()
        raise
    return get_notification_preferences(db, user_id)


def add_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    payload: dict | None = None,
    dedup_key: str | None = None,
    term_id: int | None = None,
) -> Notification | None:
    if dedup_key is not None:
        existing = db.scalar(
            select(Notification.id).where(Notification.dedup_key == dedup_key)
        )
        if existing is not None:
            return None
    notification = Notification(
        term_id=term_id or get_active_term(db).id,
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        payload_json=json.dumps(payload or {}, separators=(",", ":")),
        dedup_key=dedup_key,
    )
    if dedup_key is None:
        db.add(notification)
        return notification

    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return None
    return notification


def add_clash_report_status_notification(
    db: Session,
    *,
    user_id: int,
    report_id: int,
    status: str,
    resolution_note: str | None,
    event_key: str,
    term_id: int | None = None,
) -> Notification | None:
    preference = db.get(NotificationPreference, user_id)
    if not _preference_values(preference)["clash_report_updates_enabled"]:
        return None
    message = f"Your clash report is now {status.replace('_', ' ')}."
    if resolution_note:
        message = f"{message} {resolution_note}"
    return add_notification(
        db,
        user_id=user_id,
        notification_type="clash_report_status",
        title="Clash report updated",
        message=message,
        payload={"report_id": report_id, "status": status},
        dedup_key=f"clash-report:{report_id}:{event_key}",
        term_id=term_id,
    )


def _affected_user_ids(db: Session, entry: TimetableEntry) -> set[int]:
    if not entry.course_code:
        return set()
    course_code = entry.course_code.strip().upper()
    students = list(
        db.scalars(
            select(StudentEnrollment).where(
                StudentEnrollment.term_id == entry.term_id,
                func.upper(StudentEnrollment.course_code) == course_code
            )
        ).all()
    )
    faculty_assignments = list(
        db.scalars(
            select(FacultyClassAssignment).where(
                FacultyClassAssignment.term_id == entry.term_id,
                func.upper(FacultyClassAssignment.course_code) == course_code
            )
        ).all()
    )
    user_ids = {
        enrollment.user_id
        for enrollment in students
        if section_matches(enrollment.section, entry.section)
        and semester_matches(enrollment.semester, entry.semester)
    }
    user_ids.update(
        assignment.faculty_user_id
        for assignment in faculty_assignments
        if section_matches(assignment.section, entry.section)
        and semester_matches(assignment.semester, entry.semester)
    )
    return user_ids


def add_schedule_change_notifications(
    db: Session,
    *,
    entry: TimetableEntry,
    notification_type: str,
    title: str,
    message: str,
    event_key: str,
    change_details: dict | None = None,
) -> int:
    created_count = 0
    payload = {
        "timetable_entry_id": entry.id,
        "course_code": entry.course_code,
        "section": entry.section,
        "semester": entry.semester,
        "day": entry.day,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "room": entry.room,
        **(change_details or {}),
    }
    for user_id in _affected_user_ids(db, entry):
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            continue
        preference = db.get(NotificationPreference, user_id)
        if not _preference_values(preference)["schedule_change_enabled"]:
            continue
        created = add_notification(
            db,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            payload=payload,
            dedup_key=f"schedule-change:{user_id}:{event_key}",
            term_id=entry.term_id,
        )
        created_count += int(created is not None)
    return created_count


def add_time_change_notifications(
    db: Session,
    *,
    entry: TimetableEntry,
    old_day: str,
    old_start_time: str,
    old_end_time: str,
    event_key: str,
) -> int:
    return add_schedule_change_notifications(
        db,
        entry=entry,
        notification_type="time_change",
        title=f"Schedule changed for {entry.course_code or entry.course_name}",
        message=(
            f"Class moved from {old_day} {old_start_time}-{old_end_time} "
            f"to {entry.day} {entry.start_time}-{entry.end_time}."
        ),
        event_key=event_key,
        change_details={
            "old_day": old_day,
            "old_start_time": old_start_time,
            "old_end_time": old_end_time,
            "new_day": entry.day,
            "new_start_time": entry.start_time,
            "new_end_time": entry.end_time,
        },
    )


def _serialize_notification(notification: Notification) -> dict:
    try:
        payload = json.loads(notification.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": notification.id,
        "term_id": notification.term_id,
        "user_id": notification.user_id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "payload": payload,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


def list_notifications(
    db: Session,
    *,
    user_id: int,
    unread_only: bool = False,
    notification_type: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    filters = [Notification.user_id == user_id]
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    if notification_type is not None:
        filters.append(Notification.type == notification_type)
    total = db.scalar(select(func.count(Notification.id)).where(*filters)) or 0
    unread_count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    ) or 0
    statement = (
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
    )
    notifications = list(db.scalars(statement).all())
    return {
        "notifications": [_serialize_notification(item) for item in notifications],
        "total": total,
        "unread_count": unread_count,
        "offset": offset,
        "limit": limit,
    }


def mark_notification_read(db: Session, *, user_id: int, notification_id: int) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(notification)
    return _serialize_notification(notification)


def mark_all_notifications_read(db: Session, *, user_id: int) -> int:
    notifications = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        ).all()
    )
    read_at = datetime.now(UTC).replace(tzinfo=None)
    for notification in notifications:
        notification.read_at = read_at
    db.commit()
    return len(notifications)


def _user_timetable(db: Session, user: User):
    if user.role == "student":
        return get_student_timetable(db, user.id)
    if user.role == "faculty":
        return get_faculty_timetable(db, user.id)
    return []


def process_due_notifications(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict:
    timezone = _timezone()
    local_now = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    users = list(
        db.scalars(
            select(User).where(
                User.is_active.is_(True),
                User.role.in_(("student", "faculty")),
            )
        ).all()
    )
    reminder_count = 0
    summary_count = 0
    weekday = local_now.strftime("%A")
    for user in users:
        values = _preference_values(db.get(NotificationPreference, user.id))
        timetable = [entry for entry in _user_timetable(db, user) if entry.day == weekday]
        reminder_minutes = values["class_reminder_minutes"]
        if reminder_minutes is not None:
            for entry in timetable:
                class_time = datetime.combine(
                    local_now.date(),
                    time.fromisoformat(entry.start_time),
                    tzinfo=timezone,
                )
                minutes_until = (class_time - local_now).total_seconds() / 60
                if 0 <= minutes_until <= reminder_minutes:
                    created = add_notification(
                        db,
                        user_id=user.id,
                        notification_type="class_reminder",
                        title=f"{entry.course_code or entry.course_name} starts soon",
                        message=(
                            f"Class starts at {entry.start_time} in "
                            f"{entry.room or 'the scheduled location'}."
                        ),
                        payload={"timetable_entry_id": entry.id},
                        dedup_key=(
                            f"class-reminder:{user.id}:{entry.id}:"
                            f"{local_now.date().isoformat()}:{reminder_minutes}"
                        ),
                    )
                    reminder_count += int(created is not None)

        summary_time = time.fromisoformat(values["daily_summary_time"])
        if values["daily_summary_enabled"] and local_now.time() >= summary_time and timetable:
            courses = [entry.course_code or entry.course_name or "Class" for entry in timetable]
            created = add_notification(
                db,
                user_id=user.id,
                notification_type="daily_summary",
                title="Today's class summary",
                message=f"You have {len(timetable)} class(es): {', '.join(courses)}.",
                payload={"timetable_entry_ids": [entry.id for entry in timetable]},
                dedup_key=f"daily-summary:{user.id}:{local_now.date().isoformat()}",
            )
            summary_count += int(created is not None)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "reminders_created": reminder_count,
        "summaries_created": summary_count,
        "processed_users": len(users),
        "timezone": APP_TIMEZONE,
    }
