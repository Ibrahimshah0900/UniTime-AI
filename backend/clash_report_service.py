from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.clash_report_schemas import ClashReportCreate, ClashReportReviewUpdate
from backend.enrollment_service import get_student_timetable
from backend.models import (
    StudentClashReport,
    StudentClashReportEvent,
    StudentClashReportItem,
    TimetableEntry,
    User,
)
from backend.notification_service import add_clash_report_status_notification
from backend.term_service import get_active_term, require_active_term_id


ALLOWED_STATUS_TRANSITIONS = {
    "submitted": frozenset({"under_review", "rejected", "duplicate"}),
    "under_review": frozenset({"resolved", "rejected", "duplicate"}),
    "resolved": frozenset(),
    "rejected": frozenset(),
    "duplicate": frozenset(),
}


def _reports_overlap(entries: Sequence[TimetableEntry]) -> bool:
    for index, first in enumerate(entries):
        for second in entries[index + 1 :]:
            if first.day != second.day:
                continue
            if first.start_time < second.end_time and second.start_time < first.end_time:
                return True
    return False


def _get_items(db: Session, report_id: int) -> list[StudentClashReportItem]:
    statement = (
        select(StudentClashReportItem)
        .where(StudentClashReportItem.report_id == report_id)
        .order_by(StudentClashReportItem.id)
    )
    return list(db.scalars(statement).all())


def _get_events(db: Session, report_id: int) -> list[StudentClashReportEvent]:
    statement = (
        select(StudentClashReportEvent)
        .where(StudentClashReportEvent.report_id == report_id)
        .order_by(StudentClashReportEvent.id)
    )
    return list(db.scalars(statement).all())


def _serialize_report(
    db: Session,
    report: StudentClashReport,
    *,
    include_events: bool,
) -> dict:
    student = db.get(User, report.student_user_id)
    if student is None:
        raise HTTPException(status_code=500, detail="Report owner could not be loaded.")

    result = {
        "id": report.id,
        "term_id": report.term_id,
        "student_user_id": report.student_user_id,
        "student_name": student.full_name,
        "student_email": student.email,
        "status": report.status,
        "notes": report.notes,
        "evidence_reference": report.evidence_reference,
        "duplicate_of_report_id": report.duplicate_of_report_id,
        "resolution_note": report.resolution_note,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "items": _get_items(db, report.id),
    }
    if include_events:
        result["events"] = _get_events(db, report.id)
    return result


def create_clash_report(
    db: Session,
    *,
    student_user_id: int,
    request: ClashReportCreate,
) -> dict:
    active_term = get_active_term(db)
    personal_entries = {
        entry.id: entry for entry in get_student_timetable(db, student_user_id)
    }
    try:
        selected_entries = [
            personal_entries[entry_id] for entry_id in request.timetable_entry_ids
        ]
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "Every reported class must exist in the student's personal "
                "timetable."
            ),
        ) from exc

    if not _reports_overlap(selected_entries):
        raise HTTPException(
            status_code=422,
            detail="The selected timetable classes do not overlap.",
        )

    report = StudentClashReport(
        term_id=active_term.id,
        student_user_id=student_user_id,
        status="submitted",
        notes=request.notes,
        evidence_reference=request.evidence_reference,
    )
    db.add(report)

    try:
        db.flush()
        for entry in selected_entries:
            db.add(
                StudentClashReportItem(
                    report_id=report.id,
                    timetable_entry_id=entry.id,
                    course_code=entry.course_code or entry.course_name or "Unknown class",
                    section=entry.section,
                    semester=entry.semester,
                    day=entry.day,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                )
            )
        db.add(
            StudentClashReportEvent(
                report_id=report.id,
                actor_user_id=student_user_id,
                action="submitted",
                from_status=None,
                to_status="submitted",
                note=request.notes,
            )
        )
        db.commit()
        db.refresh(report)
    except Exception:
        db.rollback()
        raise

    return _serialize_report(db, report, include_events=True)


def get_clash_report(
    db: Session,
    report_id: int,
    *,
    student_user_id: int | None = None,
) -> dict:
    report = db.get(StudentClashReport, report_id)
    if report is None or (
        student_user_id is not None and report.student_user_id != student_user_id
    ):
        raise HTTPException(status_code=404, detail="Clash report not found.")
    return _serialize_report(db, report, include_events=True)


def list_clash_reports(
    db: Session,
    *,
    student_user_id: int | None = None,
    status: str | None = None,
    term_id: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    filters = []
    if student_user_id is not None:
        filters.append(StudentClashReport.student_user_id == student_user_id)
    if status is not None:
        filters.append(StudentClashReport.status == status)
    if term_id is not None:
        filters.append(StudentClashReport.term_id == term_id)

    count_statement = select(func.count(StudentClashReport.id)).where(*filters)
    total = db.scalar(count_statement) or 0
    statement = (
        select(StudentClashReport)
        .where(*filters)
        .order_by(StudentClashReport.created_at.desc(), StudentClashReport.id.desc())
        .offset(offset)
        .limit(limit)
    )
    reports = list(db.scalars(statement).all())
    return {
        "reports": [
            _serialize_report(db, report, include_events=False) for report in reports
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def update_clash_report(
    db: Session,
    *,
    report_id: int,
    actor_user_id: int,
    request: ClashReportReviewUpdate,
) -> dict:
    report = db.scalar(
        select(StudentClashReport)
        .where(StudentClashReport.id == report_id)
        .with_for_update()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Clash report not found.")

    require_active_term_id(db, report.term_id)

    allowed = ALLOWED_STATUS_TRANSITIONS.get(report.status, frozenset())
    if request.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Report status cannot change from {report.status} "
                f"to {request.status}."
            ),
        )

    duplicate_target = None
    if request.status == "duplicate":
        duplicate_target = db.get(StudentClashReport, request.duplicate_of_report_id)
        if duplicate_target is None:
            raise HTTPException(
                status_code=422,
                detail="Duplicate target report does not exist.",
            )
        if duplicate_target.term_id != report.term_id:
            raise HTTPException(
                status_code=422,
                detail="Duplicate reports must belong to the same academic term.",
            )
        if duplicate_target.id == report.id:
            raise HTTPException(
                status_code=422,
                detail="A report cannot be marked as a duplicate of itself.",
            )
        if duplicate_target.duplicate_of_report_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Duplicate target must be a canonical report.",
            )

    previous_status = report.status
    report.status = request.status
    report.resolution_note = request.resolution_note
    report.duplicate_of_report_id = (
        duplicate_target.id if duplicate_target is not None else None
    )
    db.add(
        event := StudentClashReportEvent(
            report_id=report.id,
            actor_user_id=actor_user_id,
            action="status_changed",
            from_status=previous_status,
            to_status=request.status,
            note=request.resolution_note,
        )
    )

    try:
        db.flush()
        add_clash_report_status_notification(
            db,
            user_id=report.student_user_id,
            report_id=report.id,
            status=request.status,
            resolution_note=request.resolution_note,
            event_key=str(event.id),
            term_id=report.term_id,
        )
        db.commit()
        db.refresh(report)
    except Exception:
        db.rollback()
        raise

    return _serialize_report(db, report, include_events=True)
