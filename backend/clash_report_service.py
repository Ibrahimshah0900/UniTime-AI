from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.clash_report_schemas import ClashReportCreate, ClashReportReviewUpdate
from backend.enrollment_service import get_student_timetable
from backend.models import (
    StudentClashReport,
    StudentClashReportEvent,
    StudentClashReportItem,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.notification_service import add_clash_report_status_notification
from backend.safe_candidate_service import generate_safe_candidates
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


def _get_verified_student_identity(
    db: Session,
    student_user_id: int,
) -> tuple[User, StudentProfile]:
    student = db.get(User, student_user_id)
    profile = db.get(StudentProfile, student_user_id)
    if (
        student is None
        or student.role != "student"
        or not student.is_active
        or student.must_change_password
        or profile is None
        or not profile.is_verified
        or not profile.onboarding_completed
        or profile.academic_status != "active"
    ):
        raise HTTPException(
            status_code=403,
            detail="An active, verified, onboarded student identity is required.",
        )
    return student, profile


def _conflict_fingerprint(entries: Sequence[TimetableEntry]) -> str:
    identity = [
        {
            "entry_id": entry.id,
            "course_code": (entry.course_code or "").strip().upper(),
            "section": (entry.section or "").strip().upper(),
            "day": entry.day,
            "start_time": entry.start_time,
            "end_time": entry.end_time,
        }
        for entry in sorted(entries, key=lambda item: item.id)
    ]
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    result = {
        "id": report.id,
        "term_id": report.term_id,
        "student_user_id": report.student_user_id,
        "student_registration_number": report.student_registration_number_snapshot,
        "student_name": report.student_name_snapshot,
        "student_email": report.student_email_snapshot,
        "student_department": report.student_department_snapshot,
        "student_program": report.student_program_snapshot,
        "student_batch": report.student_batch_snapshot,
        "student_semester": report.student_semester_snapshot,
        "student_section": report.student_section_snapshot,
        "conflict_fingerprint": report.conflict_fingerprint,
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
    student, profile = _get_verified_student_identity(db, student_user_id)
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

    if any(entry.term_id != active_term.id for entry in selected_entries):
        raise HTTPException(
            status_code=422,
            detail="Every reported class must belong to the active academic term.",
        )

    conflict_fingerprint = _conflict_fingerprint(selected_entries)
    existing_report_id = db.scalar(
        select(StudentClashReport.id).where(
            StudentClashReport.student_user_id == student_user_id,
            StudentClashReport.term_id == active_term.id,
            StudentClashReport.conflict_fingerprint == conflict_fingerprint,
        )
    )
    if existing_report_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This conflict was already reported as report {existing_report_id}.",
        )

    report = StudentClashReport(
        term_id=active_term.id,
        student_user_id=student_user_id,
        student_registration_number_snapshot=profile.registration_number,
        student_name_snapshot=student.full_name,
        student_email_snapshot=student.email,
        student_department_snapshot=profile.department,
        student_program_snapshot=profile.program,
        student_batch_snapshot=profile.batch,
        student_semester_snapshot=profile.current_semester,
        student_section_snapshot=profile.section,
        conflict_fingerprint=conflict_fingerprint,
        status="submitted",
        notes=request.notes,
        evidence_reference=request.evidence_reference,
    )
    db.add(report)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This exact conflict has already been reported.",
        ) from exc

    try:
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


def generate_clash_report_resolution_candidates(
    db: Session,
    *,
    report_id: int,
    target_entry_id: int | None = None,
    limit: int = 20,
    include_rejected_limit: int = 20,
) -> dict:
    report = db.get(StudentClashReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Clash report not found.")
    require_active_term_id(db, report.term_id)
    if report.status not in {"submitted", "under_review"}:
        raise HTTPException(
            status_code=409,
            detail="Resolution candidates are only available for open clash reports.",
        )

    report_entry_ids = [
        item.timetable_entry_id
        for item in _get_items(db, report.id)
        if item.timetable_entry_id is not None
    ]
    if len(set(report_entry_ids)) < 2:
        raise HTTPException(
            status_code=409,
            detail="The report no longer has enough current timetable references to resolve safely.",
        )

    entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == report.term_id)
            .order_by(TimetableEntry.id)
        ).all()
    )
    entry_lookup = {entry.id: entry for entry in entries}
    missing_entry_ids = set(report_entry_ids) - entry_lookup.keys()
    if missing_entry_ids:
        raise HTTPException(
            status_code=409,
            detail="One or more reported timetable entries no longer exist.",
        )
    current_report_entries = [entry_lookup[entry_id] for entry_id in report_entry_ids]
    if not _reports_overlap(current_report_entries):
        raise HTTPException(
            status_code=409,
            detail=(
                "The reported classes no longer overlap in the current timetable. "
                "Review the current state before closing the report."
            ),
        )

    if target_entry_id is not None and target_entry_id not in report_entry_ids:
        raise HTTPException(
            status_code=422,
            detail="The target entry must be one of the classes attached to this report.",
        )
    target_entry_ids = (
        [target_entry_id]
        if target_entry_id is not None
        else list(dict.fromkeys(report_entry_ids))
    )
    result = generate_safe_candidates(
        db,
        entries=entries,
        target_entry_ids=target_entry_ids,
        report_entry_ids=report_entry_ids,
        limit=limit,
        include_rejected_limit=include_rejected_limit,
    )
    return {
        "report_id": report.id,
        "report_status": report.status,
        "report_entry_ids": report_entry_ids,
        "target_entry_ids": target_entry_ids,
        **result,
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
