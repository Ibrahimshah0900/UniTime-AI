from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.config import APP_TIMEZONE
from backend.enrollment_service import get_student_timetable
from backend.faculty_service import get_faculty_timetable
from backend.models import (
    FacultyClassAssignment,
    Notification,
    StudentClashReport,
    StudentEnrollment,
    TimetableEntry,
    User,
)
from backend.term_service import get_active_term


def _unread_notifications(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    ) or 0


def get_dashboard(db: Session, user: User) -> dict:
    today = datetime.now(ZoneInfo(APP_TIMEZONE)).strftime("%A")
    active_term = get_active_term(db)
    term_context = {
        "id": active_term.id,
        "code": active_term.code,
        "name": active_term.name,
        "status": active_term.status,
    }
    if user.role == "student":
        timetable = get_student_timetable(db, user.id)
        status_rows = db.execute(
            select(StudentClashReport.status, func.count(StudentClashReport.id))
            .where(
                StudentClashReport.student_user_id == user.id,
                StudentClashReport.term_id == active_term.id,
            )
            .group_by(StudentClashReport.status)
        ).all()
        data = {
            "enrollment_count": db.scalar(
                select(func.count(StudentEnrollment.id)).where(
                    StudentEnrollment.user_id == user.id,
                    StudentEnrollment.term_id == active_term.id,
                )
            ) or 0,
            "timetable_entry_count": len(timetable),
            "classes_today": len([entry for entry in timetable if entry.day == today]),
            "clash_reports_by_status": dict(status_rows),
            "unread_notifications": _unread_notifications(db, user.id),
        }
    elif user.role == "faculty":
        timetable = get_faculty_timetable(db, user.id)
        data = {
            "assignment_count": db.scalar(
            select(func.count(FacultyClassAssignment.id)).where(
                    FacultyClassAssignment.faculty_user_id == user.id,
                    FacultyClassAssignment.term_id == active_term.id,
                )
            ) or 0,
            "timetable_entry_count": len(timetable),
            "classes_today": len([entry for entry in timetable if entry.day == today]),
            "unread_notifications": _unread_notifications(db, user.id),
        }
    elif user.role == "coordinator":
        entries = list(
            db.scalars(
                select(TimetableEntry).where(TimetableEntry.term_id == active_term.id)
            ).all()
        )
        clashes = detect_clashes(entries)
        data = {
            "timetable_entry_count": len(entries),
            "clash_count": len(clashes),
            "clashes_by_type": {
                clash_type: len([item for item in clashes if item["type"] == clash_type])
                for clash_type in ("room", "faculty", "section")
            },
            "pending_clash_reports": db.scalar(
                select(func.count(StudentClashReport.id)).where(
                    StudentClashReport.term_id == active_term.id,
                    StudentClashReport.status.in_(("submitted", "under_review"))
                )
            ) or 0,
            "unread_notifications": _unread_notifications(db, user.id),
        }
    else:
        role_rows = db.execute(
            select(User.role, func.count(User.id)).group_by(User.role)
        ).all()
        data = {
            "users_by_role": dict(role_rows),
            "active_users": db.scalar(
                select(func.count(User.id)).where(User.is_active.is_(True))
            ) or 0,
            "inactive_users": db.scalar(
                select(func.count(User.id)).where(User.is_active.is_(False))
            ) or 0,
            "timetable_entry_count": db.scalar(
                select(func.count(TimetableEntry.id)).where(
                    TimetableEntry.term_id == active_term.id
                )
            ) or 0,
            "pending_clash_reports": db.scalar(
                select(func.count(StudentClashReport.id)).where(
                    StudentClashReport.term_id == active_term.id,
                    StudentClashReport.status.in_(("submitted", "under_review"))
                )
            ) or 0,
            "unread_notifications": _unread_notifications(db, user.id),
        }
    data["active_term"] = term_context
    return {"role": user.role, "generated_for_day": today, "data": data}
