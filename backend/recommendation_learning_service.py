from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.learning_event_service import record_learning_event, stable_learning_key
from backend.models import LearningEvent, StudentClashReport


ELIGIBLE_RANKING_STATUSES = frozenset({"SAFE", "CONDITIONALLY_SAFE"})


def _context(event: LearningEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.context_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _report_key(report_id: int) -> str:
    return stable_learning_key("clash_report", report_id)


def record_resolution_candidate_impression(
    db: Session,
    *,
    report_id: int,
    actor_user_id: int,
    actor_role: str,
    result: Mapping[str, Any],
) -> str:
    """Persist one PII-free candidate-view impression from the review API."""
    report = db.get(StudentClashReport, report_id)
    if report is None:
        raise ValueError("Clash report not found while recording candidate impression.")

    impression_key = uuid.uuid4().hex
    reviewer_key = stable_learning_key("reviewer", actor_user_id)
    report_key = _report_key(report.id)
    candidates = list(result.get("candidates") or [])
    rejected = list(result.get("rejected_candidates") or [])
    summary = dict(result.get("summary") or {})

    record_learning_event(
        db,
        term_id=report.term_id,
        event_type="recommendation_generated",
        subject_key=stable_learning_key("student", report.student_user_id),
        entity_type="clash_report",
        entity_key=report_key,
        actor_role=actor_role,
        source="resolution_candidates_api",
        outcome_label="candidate_set_generated",
        context={
            "impression_key": impression_key,
            "reviewer_key": reviewer_key,
            "candidate_count": len(candidates),
            "rejected_candidate_count": len(rejected),
            "target_entry_count": len(result.get("target_entry_ids") or []),
            "summary": {
                "generated": int(summary.get("generated", 0)),
                "safe": int(summary.get("safe", 0)),
                "conditionally_safe": int(summary.get("conditionally_safe", 0)),
                "insufficient_data": int(summary.get("insufficient_data", 0)),
                "rejected": int(summary.get("rejected", 0)),
            },
        },
    )

    for position, candidate in enumerate(candidates, start=1):
        ranker = dict(candidate.get("ranker") or {})
        features = dict(candidate.get("features") or {})
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="recommendation_shown",
            subject_key=stable_learning_key("student", report.student_user_id),
            entity_type="clash_report",
            entity_key=report_key,
            actor_role=actor_role,
            source="resolution_candidates_api",
            outcome_label="shown",
            context={
                "impression_key": impression_key,
                "reviewer_key": reviewer_key,
                "candidate_id": candidate["candidate_id"],
                "position": position,
                "safety_status": candidate["status"],
                "ranker_id": ranker.get("ranker_id"),
                "ranker_version": ranker.get("ranker_version"),
                "rank_score": candidate.get("rank_score"),
                "feature_schema_version": features.get("feature_schema_version"),
                "features": features,
            },
        )

    # Returned hard-rejected examples are explicitly marked as deterministic
    # hard-filter outcomes. They are never eligible ranker negatives.
    for position, candidate in enumerate(rejected, start=1):
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="recommendation_rejected",
            subject_key=stable_learning_key("student", report.student_user_id),
            entity_type="clash_report",
            entity_key=report_key,
            actor_role=actor_role,
            source="resolution_candidates_api",
            outcome_label="hard_constraint_rejected",
            context={
                "impression_key": impression_key,
                "reviewer_key": reviewer_key,
                "candidate_id": candidate["candidate_id"],
                "position": position,
                "safety_status": "REJECTED",
                "rejection_reason_count": len(candidate.get("rejection_reasons") or []),
                "eligible_for_ranker_training": False,
            },
        )

    db.commit()
    return impression_key


def _latest_candidate_impression(
    db: Session,
    *,
    report_id: int,
    candidate_id: str,
    actor_user_id: int,
) -> tuple[str | None, list[LearningEvent]]:
    report_key = _report_key(report_id)
    shown_events = list(
        db.scalars(
            select(LearningEvent)
            .where(
                LearningEvent.event_type == "recommendation_shown",
                LearningEvent.entity_type == "clash_report",
                LearningEvent.entity_key == report_key,
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
        ).all()
    )
    selected_impression: str | None = None
    reviewer_key = stable_learning_key("reviewer", actor_user_id)
    for event in shown_events:
        context = _context(event)
        if (
            context.get("candidate_id") == candidate_id
            and context.get("reviewer_key") == reviewer_key
        ):
            selected_impression = context.get("impression_key")
            break
    return selected_impression, shown_events


def record_resolution_candidate_choice(
    db: Session,
    *,
    report: StudentClashReport,
    actor_user_id: int,
    actor_role: str | None,
    schedule_change_key: str,
    selected_candidate: Mapping[str, Any],
) -> None:
    """Link a selected candidate to its latest observed impression and alternatives."""
    selected_candidate_id = str(selected_candidate["candidate_id"])
    impression_key, shown_events = _latest_candidate_impression(
        db,
        report_id=report.id,
        candidate_id=selected_candidate_id,
        actor_user_id=actor_user_id,
    )
    ranker = dict(selected_candidate.get("ranker") or {})
    features = dict(selected_candidate.get("features") or {})

    record_learning_event(
        db,
        term_id=report.term_id,
        event_type="recommendation_selected",
        subject_key=stable_learning_key("student", report.student_user_id),
        entity_type="schedule_change",
        entity_key=schedule_change_key,
        actor_role=actor_role,
        outcome_label="selected_and_applied",
        context={
            "impression_key": impression_key,
            "reviewer_key": stable_learning_key("reviewer", actor_user_id),
            "impression_observed": impression_key is not None,
            "candidate_id": selected_candidate_id,
            "safety_status": selected_candidate["status"],
            "ranker_id": ranker.get("ranker_id"),
            "ranker_version": ranker.get("ranker_version"),
            "rank_score": selected_candidate.get("rank_score"),
            "feature_schema_version": features.get("feature_schema_version"),
            "features": features,
        },
    )

    if impression_key is None:
        return

    rejected_candidate_ids: set[str] = set()
    for shown_event in shown_events:
        shown_context = _context(shown_event)
        if shown_context.get("impression_key") != impression_key:
            continue
        alternative_id = str(shown_context.get("candidate_id") or "")
        safety_status = shown_context.get("safety_status")
        if (
            not alternative_id
            or alternative_id == selected_candidate_id
            or alternative_id in rejected_candidate_ids
            or safety_status not in ELIGIBLE_RANKING_STATUSES
        ):
            continue
        rejected_candidate_ids.add(alternative_id)
        record_learning_event(
            db,
            term_id=report.term_id,
            event_type="recommendation_rejected",
            subject_key=stable_learning_key("student", report.student_user_id),
            entity_type="clash_report",
            entity_key=_report_key(report.id),
            actor_role=actor_role,
            outcome_label="not_selected",
            context={
                "impression_key": impression_key,
                "reviewer_key": stable_learning_key("reviewer", actor_user_id),
                "candidate_id": alternative_id,
                "safety_status": safety_status,
                "position": shown_context.get("position"),
                "ranker_id": shown_context.get("ranker_id"),
                "ranker_version": shown_context.get("ranker_version"),
                "rank_score": shown_context.get("rank_score"),
                "feature_schema_version": shown_context.get("feature_schema_version"),
                "features": shown_context.get("features") or {},
                "eligible_for_ranker_training": True,
            },
        )
