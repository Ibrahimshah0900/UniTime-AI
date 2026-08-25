from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.clash_report_schemas import (
    ClashReportCreate,
    ClashReportResolutionApplyRequest,
    ClashReportReviewUpdate,
)
from backend.enrollment_conflict_graph import (
    build_enrollment_conflict_analysis,
    build_enrollment_conflict_evidence,
)
from backend.enrollment_service import get_student_timetable
from backend.models import (
    StudentClashReport,
    StudentClashReportEvent,
    StudentClashReportItem,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.learning_event_service import record_learning_event, stable_learning_key
from backend.notification_service import (
    add_clash_report_status_notification,
    add_time_change_notifications,
)
from backend.safe_candidate_service import (
    calculate_weighted_risk_cost,
    generate_safe_candidates,
)
from backend.student_resolution_applier import (
    StudentScheduleChange,
    create_resolution_learning_event,
)
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
        "resolution_reason": report.resolution_reason,
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
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="clash_report_submitted",
            subject_key=stable_learning_key("student", student_user_id),
            entity_type="clash_report",
            entity_key=stable_learning_key("clash_report", report.id),
            actor_role="student",
            outcome_label="submitted",
            context={
                "conflict_fingerprint": report.conflict_fingerprint,
                "reported_entry_count": len(selected_entries),
                "has_notes": request.notes is not None,
                "has_evidence_reference": request.evidence_reference is not None,
            },
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


def list_clash_report_clusters(
    db: Session,
    *,
    term_id: int,
    open_only: bool = True,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    reports = list(
        db.scalars(
            select(StudentClashReport)
            .where(StudentClashReport.term_id == term_id)
            .order_by(StudentClashReport.created_at, StudentClashReport.id)
        ).all()
    )
    if not reports:
        return {"clusters": [], "total": 0, "offset": offset, "limit": limit}

    report_ids = [report.id for report in reports]
    items = list(
        db.scalars(
            select(StudentClashReportItem)
            .where(StudentClashReportItem.report_id.in_(report_ids))
            .order_by(StudentClashReportItem.report_id, StudentClashReportItem.id)
        ).all()
    )
    items_by_report: dict[int, list[StudentClashReportItem]] = defaultdict(list)
    for item in items:
        items_by_report[item.report_id].append(item)

    entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == term_id)
            .order_by(TimetableEntry.id)
        ).all()
    )
    entry_lookup = {entry.id: entry for entry in entries}
    evidence = build_enrollment_conflict_evidence(db, entries, term_id=term_id)

    reports_by_fingerprint: dict[str, list[StudentClashReport]] = defaultdict(list)
    for report in reports:
        reports_by_fingerprint[report.conflict_fingerprint].append(report)

    open_statuses = {"submitted", "under_review"}
    clusters: list[dict] = []
    for fingerprint, grouped_reports in reports_by_fingerprint.items():
        open_reports = [
            report for report in grouped_reports if report.status in open_statuses
        ]
        if open_only and not open_reports:
            continue

        canonical_items = items_by_report[grouped_reports[0].id]
        timetable_entry_ids = list(
            dict.fromkeys(
                item.timetable_entry_id
                for item in canonical_items
                if item.timetable_entry_id is not None
            )
        )
        current_entries = [
            entry_lookup[entry_id]
            for entry_id in timetable_entry_ids
            if entry_id in entry_lookup
        ]
        covered_ids = [
            entry_id
            for entry_id in timetable_entry_ids
            if entry_id in evidence.entry_students
        ]
        if timetable_entry_ids and len(covered_ids) == len(timetable_entry_ids):
            enrollment_coverage = "complete"
        elif covered_ids:
            enrollment_coverage = "partial"
        else:
            enrollment_coverage = "none"

        affected_students: set[int] = set()
        if timetable_entry_ids:
            affected_students = set(
                evidence.entry_students.get(timetable_entry_ids[0], frozenset())
            )
            for entry_id in timetable_entry_ids[1:]:
                affected_students.intersection_update(
                    evidence.entry_students.get(entry_id, frozenset())
                )

        status_counts = Counter(report.status for report in grouped_reports)
        clusters.append(
            {
                "term_id": term_id,
                "conflict_fingerprint": fingerprint,
                "report_ids": sorted(report.id for report in grouped_reports),
                "open_report_ids": sorted(report.id for report in open_reports),
                "timetable_entry_ids": timetable_entry_ids,
                "reported_classes": [
                    {
                        "timetable_entry_id": item.timetable_entry_id,
                        "course_code": item.course_code,
                        "section": item.section,
                        "semester": item.semester,
                        "day": item.day,
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                    }
                    for item in canonical_items
                ],
                "report_count": len(grouped_reports),
                "open_report_count": len(open_reports),
                "reporting_student_count": len(
                    {report.student_user_id for report in grouped_reports}
                ),
                "verified_affected_student_count": len(affected_students),
                "enrollment_coverage": enrollment_coverage,
                "current_timetable_overlap": (
                    len(current_entries) == len(timetable_entry_ids)
                    and _reports_overlap(current_entries)
                ),
                "status_counts": {
                    status: status_counts.get(status, 0)
                    for status in (
                        "submitted",
                        "under_review",
                        "resolved",
                        "rejected",
                        "duplicate",
                    )
                },
                "first_reported_at": min(
                    report.created_at for report in grouped_reports
                ),
                "latest_reported_at": max(
                    report.created_at for report in grouped_reports
                ),
            }
        )

    clusters.sort(
        key=lambda cluster: (
            cluster["latest_reported_at"],
            cluster["conflict_fingerprint"],
        ),
        reverse=True,
    )
    total = len(clusters)
    return {
        "clusters": clusters[offset : offset + limit],
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


def apply_clash_report_resolution_candidate(
    db: Session,
    *,
    report_id: int,
    candidate_id: str,
    actor_user_id: int,
    request: ClashReportResolutionApplyRequest,
) -> dict:
    try:
        report = db.scalar(
            select(StudentClashReport)
            .where(StudentClashReport.id == report_id)
            .with_for_update()
        )
        if report is None:
            raise HTTPException(status_code=404, detail="Clash report not found.")
        require_active_term_id(db, report.term_id)
        if report.status != "under_review":
            raise HTTPException(
                status_code=409,
                detail="Move the report to under_review before applying a resolution.",
            )

        entry = db.scalar(
            select(TimetableEntry)
            .where(
                TimetableEntry.id == request.target_entry_id,
                TimetableEntry.term_id == report.term_id,
            )
            .with_for_update()
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail="The candidate timetable entry no longer exists.",
            )

        live_result = generate_clash_report_resolution_candidates(
            db,
            report_id=report.id,
            target_entry_id=request.target_entry_id,
            limit=100,
            include_rejected_limit=0,
        )
        candidate = next(
            (
                item
                for item in live_result["candidates"]
                if item["candidate_id"] == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The selected candidate is stale or no longer passes current "
                    "hard safety checks. Generate fresh candidates."
                ),
            )
        if candidate["status"] == "INSUFFICIENT_DATA":
            raise HTTPException(
                status_code=409,
                detail=(
                    "This candidate cannot be applied because required scheduling "
                    "or enrollment data is missing."
                ),
            )
        if (
            candidate["status"] == "CONDITIONALLY_SAFE"
            and not request.confirm_conditional
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This candidate requires explicit coordinator confirmation of "
                    "the listed metadata limitations."
                ),
            )

        previous_change = db.scalar(
            select(StudentScheduleChange)
            .where(
                StudentScheduleChange.report_id == report.id,
                StudentScheduleChange.candidate_id == candidate_id,
            )
            .order_by(StudentScheduleChange.id.desc())
        )
        if previous_change is not None:
            message = (
                "This candidate was previously undone; use the history redo action."
                if previous_change.undone
                else "This candidate already has an active history record."
            )
            raise HTTPException(status_code=409, detail=message)

        old_day = entry.day
        old_start_time = entry.start_time
        old_end_time = entry.end_time
        destination = candidate["move_to"]
        entry.day = destination["day"]
        entry.start_time = destination["start_time"]
        entry.end_time = destination["end_time"]
        db.flush()

        entries_after = list(
            db.scalars(
                select(TimetableEntry)
                .where(TimetableEntry.term_id == report.term_id)
                .order_by(TimetableEntry.id)
            ).all()
        )
        analysis_after = build_enrollment_conflict_analysis(
            db,
            entries_after,
            term_id=report.term_id,
        )
        risks_after = analysis_after["risks"]
        clashes_after = detect_clashes(entries_after)
        target_clashes = [
            clash
            for clash in clashes_after
            if entry.id in {clash["entry_1"]["id"], clash["entry_2"]["id"]}
        ]
        report_entry_ids = set(live_result["report_entry_ids"])
        report_entries_after = [
            current for current in entries_after if current.id in report_entry_ids
        ]
        impact = candidate["impact"]
        live_result_changed = (
            target_clashes
            or _reports_overlap(report_entries_after)
            or len(clashes_after) != impact["structural_clashes_after"]
            or len(risks_after) != impact["student_risks_after"]
            or calculate_weighted_risk_cost(risks_after)
            != impact["weighted_risk_after"]
        )
        if live_result_changed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The live timetable changed during final validation. "
                    "No resolution was applied."
                ),
            )

        reasons = [
            component["explanation"]
            for component in candidate["score_components"]
        ]
        reasons.extend(candidate["missing_data"])
        history = StudentScheduleChange(
            term_id=report.term_id,
            entry_id=entry.id,
            group_id=None,
            report_id=report.id,
            actor_user_id=actor_user_id,
            candidate_id=candidate_id,
            safety_status=candidate["status"],
            report_resolution_note=request.resolution_note,
            change_type="clash_report_resolution",
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
            new_day=entry.day,
            new_start_time=entry.start_time,
            new_end_time=entry.end_time,
            score=float(candidate["rank_score"]),
            reasons_json=json.dumps(reasons),
            risk_cost_before=impact["weighted_risk_before"],
            risk_cost_after=impact["weighted_risk_after"],
            total_risks_before=impact["student_risks_before"],
            total_risks_after=impact["student_risks_after"],
            undone=False,
        )
        db.add(history)
        related_reports = list(
            db.scalars(
                select(StudentClashReport)
                .where(
                    StudentClashReport.term_id == report.term_id,
                    StudentClashReport.conflict_fingerprint
                    == report.conflict_fingerprint,
                    StudentClashReport.status.in_(("submitted", "under_review")),
                )
                .order_by(StudentClashReport.id)
                .with_for_update()
            ).all()
        )
        report_events: list[
            tuple[StudentClashReport, StudentClashReportEvent]
        ] = []
        for related_report in related_reports:
            previous_status = related_report.status
            related_report.status = "resolved"
            related_report.resolution_note = request.resolution_note
            related_report.resolution_reason = "timetable_changed"
            event = StudentClashReportEvent(
                report_id=related_report.id,
                actor_user_id=actor_user_id,
                action=(
                    "resolution_applied"
                    if related_report.id == report.id
                    else "resolved_by_shared_timetable_change"
                ),
                from_status=previous_status,
                to_status="resolved",
                note=request.resolution_note,
            )
            db.add(event)
            report_events.append((related_report, event))
        db.flush()
        actor = db.get(User, actor_user_id)
        for resolved_report, _event in report_events:
            record_learning_event(
                db,
                term_id=resolved_report.term_id,
                event_type="clash_report_verified",
                subject_key=stable_learning_key(
                    "student", resolved_report.student_user_id
                ),
                entity_type="clash_report",
                entity_key=stable_learning_key(
                    "clash_report", resolved_report.id
                ),
                actor_role=actor.role if actor is not None else None,
                outcome_label="resolved",
                context={
                    "from_status": _event.from_status,
                    "to_status": "resolved",
                    "resolution_reason": "timetable_changed",
                    "shared_resolution": resolved_report.id != report.id,
                },
            )
        create_resolution_learning_event(
            db,
            change=history,
            event_type="candidate_applied",
            outcome_label="accepted",
            actor_user_id=actor_user_id,
            candidate=candidate,
        )
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="resolution_applied",
            subject_key=stable_learning_key("student", report.student_user_id),
            entity_type="schedule_change",
            entity_key=stable_learning_key("schedule_change", history.id),
            actor_role=actor.role if actor is not None else None,
            outcome_label="accepted",
            context={
                "safety_status": candidate["status"],
                "ranker_id": candidate["ranker"]["ranker_id"],
                "ranker_version": candidate["ranker"]["ranker_version"],
                "rank_score": candidate["rank_score"],
                "resolved_report_count": len(report_events),
                "weighted_risk_before": impact["weighted_risk_before"],
                "weighted_risk_after": impact["weighted_risk_after"],
            },
        )
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="recommendation_selected",
            subject_key=stable_learning_key("student", report.student_user_id),
            entity_type="schedule_change",
            entity_key=stable_learning_key("schedule_change", history.id),
            actor_role=actor.role if actor is not None else None,
            outcome_label="selected_and_applied",
            context={
                "safety_status": candidate["status"],
                "ranker_id": candidate["ranker"]["ranker_id"],
                "ranker_version": candidate["ranker"]["ranker_version"],
                "rank_score": candidate["rank_score"],
                "feature_schema_version": candidate["features"][
                    "feature_schema_version"
                ],
            },
        )
        add_time_change_notifications(
            db,
            entry=entry,
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
            event_key=f"clash-report-resolution:{history.id}",
        )
        for resolved_report, event in report_events:
            add_clash_report_status_notification(
                db,
                user_id=resolved_report.student_user_id,
                report_id=resolved_report.id,
                status="resolved",
                resolution_note=request.resolution_note,
                event_key=str(event.id),
                term_id=resolved_report.term_id,
            )
        db.commit()
        db.refresh(report)
        db.refresh(history)
        resolved_report_ids = [
            resolved_report.id for resolved_report, _event in report_events
        ]
        return {
            "success": True,
            "message": "Clash-report resolution applied successfully.",
            "report_id": report.id,
            "report_status": report.status,
            "change_id": history.id,
            "candidate_id": candidate_id,
            "safety_status": candidate["status"],
            "conditional_confirmation_recorded": (
                candidate["status"] == "CONDITIONALLY_SAFE"
                and request.confirm_conditional
            ),
            "resolved_report_ids": resolved_report_ids,
            "resolved_report_count": len(resolved_report_ids),
            "applied_candidate": candidate,
            "report": _serialize_report(db, report, include_events=True),
        }
    except Exception:
        db.rollback()
        raise


def _validate_verified_resolution(
    db: Session,
    *,
    report: StudentClashReport,
    resolution_reason: str,
) -> None:
    report_entry_ids = {
        item.timetable_entry_id
        for item in _get_items(db, report.id)
        if item.timetable_entry_id is not None
    }
    current_entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(
                TimetableEntry.term_id == report.term_id,
                TimetableEntry.id.in_(report_entry_ids),
            )
            .order_by(TimetableEntry.id)
        ).all()
    )
    personal_entries = [
        entry
        for entry in get_student_timetable(db, report.student_user_id)
        if entry.id in report_entry_ids
    ]

    if _reports_overlap(personal_entries):
        raise HTTPException(
            status_code=409,
            detail=(
                "This verified student's reported personal timetable conflict still "
                "exists. Apply a safe timetable resolution or correct the student's "
                "enrollment before resolving the report."
            ),
        )
    if resolution_reason == "timetable_changed" and _reports_overlap(
        current_entries
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "resolution_reason timetable_changed is not verified because the "
                "reported institutional timetable entries still overlap."
            ),
        )
    if resolution_reason in {"enrollment_corrected", "course_dropped"} and len(
        personal_entries
    ) >= 2:
        raise HTTPException(
            status_code=409,
            detail=(
                f"resolution_reason {resolution_reason} is not verified because the "
                "student still has at least two reported classes in the personal "
                "timetable."
            ),
        )


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

    if request.status == "resolved":
        _validate_verified_resolution(
            db,
            report=report,
            resolution_reason=request.resolution_reason,
        )

    previous_status = report.status
    report.status = request.status
    report.resolution_note = request.resolution_note
    report.resolution_reason = request.resolution_reason
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
        learning_event_type = {
            "resolved": "clash_report_verified",
            "rejected": "clash_report_invalid",
            "duplicate": "clash_report_duplicate",
        }.get(request.status)
        if learning_event_type is not None:
            actor = db.get(User, actor_user_id)
            record_learning_event(
                db,
                term_id=report.term_id,
                event_type=learning_event_type,
                subject_key=stable_learning_key(
                    "student", report.student_user_id
                ),
                entity_type="clash_report",
                entity_key=stable_learning_key("clash_report", report.id),
                actor_role=actor.role if actor is not None else None,
                outcome_label=request.status,
                context={
                    "from_status": previous_status,
                    "to_status": request.status,
                    "resolution_reason": request.resolution_reason,
                    "has_resolution_note": request.resolution_note is not None,
                    "is_duplicate": request.status == "duplicate",
                },
            )
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
