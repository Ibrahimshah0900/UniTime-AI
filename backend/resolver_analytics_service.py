from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.clash_report_service import list_clash_report_clusters
from backend.enrollment_conflict_graph import build_enrollment_conflict_analysis
from backend.models import (
    AcademicTerm,
    LearningEvent,
    StudentClashReport,
    StudentClashReportEvent,
    TimetableEntry,
)
from backend.student_resolution_applier import ResolutionLearningEvent
from backend.term_service import get_active_term, get_term


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _rate(numerator: int, denominator: int, *, unavailable_reason: str | None = None) -> dict:
    if unavailable_reason is not None:
        return {
            "value": None,
            "numerator": None,
            "denominator": None,
            "available": False,
            "reason": unavailable_reason,
        }
    if denominator == 0:
        return {
            "value": None,
            "numerator": numerator,
            "denominator": denominator,
            "available": True,
            "reason": "No eligible denominator events exist yet.",
        }
    return {
        "value": round((numerator / denominator) * 100.0, 2),
        "numerator": numerator,
        "denominator": denominator,
        "available": True,
        "reason": None,
    }


def build_resolver_analytics(db: Session, *, term_id: int | None = None) -> dict:
    term: AcademicTerm = get_active_term(db) if term_id is None else get_term(db, term_id)
    entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == term.id)
            .order_by(TimetableEntry.id)
        ).all()
    )
    conflict_analysis = build_enrollment_conflict_analysis(db, entries, term_id=term.id)
    risks = conflict_analysis["risks"]
    coverage = conflict_analysis["coverage"]
    confirmed = [risk for risk in risks if risk["risk_level"] == "confirmed"]
    inferred = [risk for risk in risks if risk["risk_level"] != "confirmed"]

    reports = list(
        db.scalars(
            select(StudentClashReport)
            .where(StudentClashReport.term_id == term.id)
            .order_by(StudentClashReport.id)
        ).all()
    )
    status_counts = Counter(report.status for report in reports)

    clusters = list_clash_report_clusters(
        db,
        term_id=term.id,
        open_only=False,
        offset=0,
        limit=max(len(reports), 1),
    )["clusters"]
    grouped_duplicate_reports = sum(
        max(int(cluster["report_count"]) - 1, 0)
        for cluster in clusters
        if int(cluster["report_count"]) > 1
    )

    report_ids = [report.id for report in reports]
    events = []
    if report_ids:
        events = list(
            db.scalars(
                select(StudentClashReportEvent)
                .where(StudentClashReportEvent.report_id.in_(report_ids))
                .order_by(StudentClashReportEvent.created_at, StudentClashReportEvent.id)
            ).all()
        )
    first_resolved_at: dict[int, datetime] = {}
    shared_resolved_report_ids: set[int] = set()
    for event in events:
        if event.to_status == "resolved" and event.report_id not in first_resolved_at:
            first_resolved_at[event.report_id] = event.created_at
        if event.action == "resolved_by_shared_timetable_change":
            shared_resolved_report_ids.add(event.report_id)
    resolution_durations = []
    report_lookup = {report.id: report for report in reports}
    for report_id, resolved_at in first_resolved_at.items():
        created = report_lookup[report_id].created_at
        seconds = max((resolved_at - created).total_seconds(), 0.0)
        resolution_durations.append(seconds / 3600.0)
    average_resolution_hours = (
        round(sum(resolution_durations) / len(resolution_durations), 3)
        if resolution_durations
        else None
    )

    learning_events = list(
        db.scalars(
            select(ResolutionLearningEvent)
            .where(ResolutionLearningEvent.term_id == term.id)
            .order_by(ResolutionLearningEvent.id)
        ).all()
    )
    applied_change_ids = {
        event.change_id for event in learning_events if event.event_type == "candidate_applied"
    }
    undone_change_ids = {
        event.change_id for event in learning_events if event.event_type == "resolution_undone"
    }
    redone_change_ids = {
        event.change_id for event in learning_events if event.event_type == "resolution_redone"
    }
    resolution_applications = len(applied_change_ids)
    resolution_undos = len(undone_change_ids)
    resolution_redos = len(redone_change_ids)

    confirmed_removed = 0
    structural_removed = 0
    for event in learning_events:
        if event.event_type != "candidate_applied":
            continue
        try:
            features = json.loads(event.features_json)
        except (TypeError, json.JSONDecodeError):
            continue
        confirmed_removed += max(int(features.get("confirmed_conflicts_removed", 0)), 0)
        structural_removed += max(int(features.get("structural_clashes_removed", 0)), 0)

    shared_resolved_reports = len(shared_resolved_report_ids)
    ever_resolved_reports = len(first_resolved_at)
    shared_resolution_percentage = (
        round((shared_resolved_reports / ever_resolved_reports) * 100.0, 2)
        if ever_resolved_reports
        else None
    )

    # Candidate-review API calls now persist one recommendation_generated event
    # per observed impression and one recommendation_shown event per returned
    # candidate, so generated impressions are a real acceptance denominator.
    term_learning_events = list(
        db.scalars(
            select(LearningEvent).where(LearningEvent.term_id == term.id)
        ).all()
    )
    domain_event_types = Counter(event.event_type for event in term_learning_events)
    selected = 0
    for event in term_learning_events:
        if event.event_type != "recommendation_selected":
            continue
        try:
            context = json.loads(event.context_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(context, dict) and context.get("impression_observed") is True:
            selected += 1
    generated = int(domain_event_types.get("recommendation_generated", 0))
    if generated:
        acceptance_rate = _rate(selected, generated)
    else:
        acceptance_rate = _rate(
            0,
            0,
            unavailable_reason=(
                "No instrumented candidate-review impression has been recorded for this term yet."
            ),
        )

    return {
        "term_id": term.id,
        "term_code": term.code,
        "generated_at": _utc_now(),
        "current_confirmed_conflicts": len(confirmed),
        "current_inferred_conflicts": len(inferred),
        "current_structural_clashes": len(detect_clashes(entries)),
        "current_verified_students": int(coverage.get("verified_students", 0)),
        "current_enrollment_records": int(coverage.get("enrollment_records", 0)),
        "current_affected_student_instances": sum(
            int(risk.get("affected_student_count", 0)) for risk in confirmed
        ),
        "report_status_counts": {
            status: int(status_counts.get(status, 0))
            for status in ("submitted", "under_review", "resolved", "rejected", "duplicate")
        },
        "report_total": len(reports),
        "report_cluster_count": len(clusters),
        "grouped_duplicate_reports": grouped_duplicate_reports,
        "average_first_resolution_hours": average_resolution_hours,
        "resolution_applications": resolution_applications,
        "resolution_undos": resolution_undos,
        "resolution_redos": resolution_redos,
        "confirmed_conflicts_removed_by_applications": confirmed_removed,
        "structural_clashes_removed_by_applications": structural_removed,
        "shared_resolved_reports": shared_resolved_reports,
        "shared_resolution_percentage": shared_resolution_percentage,
        "recommendation_acceptance_rate": acceptance_rate,
        "undo_rate": _rate(resolution_undos, resolution_applications),
        "redo_rate": _rate(resolution_redos, resolution_undos),
        "important_note": (
            "Current conflict counts are recomputed from live term data. Lifetime resolution "
            "counts come from persisted resolution-learning/report events. Metrics with no "
            "trustworthy denominator are explicitly unavailable rather than estimated."
        ),
    }
