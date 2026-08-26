from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.candidate_ranker import CandidateFeatures
from backend.models import LearningEvent
from backend.student_resolution_applier import ResolutionLearningEvent


DATASET_SCHEMA_VERSION = "1.0"


def _serialize_timestamp(value) -> str:
    return value.isoformat() if value is not None else ""


def build_ranker_dataset(
    db: Session,
    *,
    term_id: int | None = None,
) -> dict:
    statement = select(ResolutionLearningEvent).order_by(
        ResolutionLearningEvent.change_id,
        ResolutionLearningEvent.id,
    )
    if term_id is not None:
        statement = statement.where(ResolutionLearningEvent.term_id == term_id)
    events = list(db.scalars(statement).all())

    events_by_change: dict[int, list[ResolutionLearningEvent]] = defaultdict(list)
    for event in events:
        events_by_change[event.change_id].append(event)

    rows: list[dict] = []
    for example_number, (change_id, change_events) in enumerate(
        sorted(events_by_change.items()),
        start=1,
    ):
        applied_events = [
            event for event in change_events if event.event_type == "candidate_applied"
        ]
        if len(applied_events) != 1:
            raise ValueError(
                f"Change {change_id} must have exactly one candidate_applied event."
            )
        applied = applied_events[0]
        latest = change_events[-1]
        features = CandidateFeatures.model_validate_json(applied.features_json)
        if not features.hard_constraints_passed:
            raise ValueError("Learning data cannot contain candidates that failed hard checks.")
        if features.feature_schema_version != applied.feature_schema_version:
            raise ValueError(
                f"Change {change_id} has inconsistent feature schema versions."
            )
        row = {
            "dataset_schema_version": DATASET_SCHEMA_VERSION,
            "example_id": f"example-{example_number:06d}",
            **features.model_dump(),
            "ranker_id": applied.ranker_id,
            "ranker_version": applied.ranker_version,
            "rank_score": applied.rank_score,
            "outcome_label": latest.outcome_label,
            "outcome_event_count": len(change_events),
            "applied_at": _serialize_timestamp(applied.created_at),
            "latest_outcome_at": _serialize_timestamp(latest.created_at),
        }
        rows.append(row)

    label_counts = Counter(row["outcome_label"] for row in rows)
    return {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "feature_schema_version": "1.0",
        "total_examples": len(rows),
        "label_counts": dict(sorted(label_counts.items())),
        "rows": rows,
        "important_note": (
            "This export contains deterministic, PII-free feature snapshots from "
            "real resolution actions. It is input for manual review only and does "
            "not establish model quality or authorize an ML deployment."
        ),
    }


def ranker_dataset_to_csv(dataset: dict) -> str:
    rows = dataset["rows"]
    if not rows:
        return ""
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


RECOMMENDATION_CHOICE_DATASET_SCHEMA_VERSION = "1.0"
ELIGIBLE_RECOMMENDATION_STATUSES = frozenset({"SAFE", "CONDITIONALLY_SAFE"})


def build_recommendation_choice_dataset(
    db: Session,
    *,
    term_id: int | None = None,
) -> dict:
    """Build groupwise PII-free ranking examples from observed coordinator choices."""
    statement = select(LearningEvent).where(
        LearningEvent.event_type.in_(
            (
                "recommendation_shown",
                "recommendation_selected",
                "recommendation_rejected",
                "resolution_undone",
                "resolution_redone",
            )
        )
    )
    if term_id is not None:
        statement = statement.where(LearningEvent.term_id == term_id)
    events = list(
        db.scalars(statement.order_by(LearningEvent.created_at, LearningEvent.id)).all()
    )

    impressions: dict[str, dict] = defaultdict(
        lambda: {"shown": {}, "selected": None, "rejected": set()}
    )
    schedule_outcomes: dict[str, str] = {}
    for event in events:
        try:
            context = json.loads(event.context_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(context, dict):
            continue
        if event.event_type in {"resolution_undone", "resolution_redone"}:
            schedule_outcomes[event.entity_key] = event.outcome_label or event.event_type
            continue
        impression_key = context.get("impression_key")
        candidate_id = context.get("candidate_id")
        if not impression_key or not candidate_id:
            continue
        group = impressions[str(impression_key)]
        if event.event_type == "recommendation_shown":
            group["shown"][str(candidate_id)] = {
                "context": context,
                "created_at": event.created_at,
            }
        elif event.event_type == "recommendation_selected":
            group["selected"] = {
                "candidate_id": str(candidate_id),
                "schedule_change_key": event.entity_key,
                "created_at": event.created_at,
            }
        elif (
            event.event_type == "recommendation_rejected"
            and event.outcome_label == "not_selected"
        ):
            group["rejected"].add(str(candidate_id))

    rows: list[dict] = []
    complete_group_count = 0
    for group_number, impression_key in enumerate(sorted(impressions), start=1):
        group = impressions[impression_key]
        selected = group["selected"]
        if selected is None:
            continue
        selected_id = selected["candidate_id"]
        eligible_shown = {
            candidate_id: item
            for candidate_id, item in group["shown"].items()
            if item["context"].get("safety_status") in ELIGIBLE_RECOMMENDATION_STATUSES
            and item["context"].get("features")
        }
        if selected_id not in eligible_shown or len(eligible_shown) < 2:
            continue
        complete_group_count += 1
        decision_group_id = f"choice-{complete_group_count:06d}"
        final_selected_outcome = schedule_outcomes.get(
            selected["schedule_change_key"], "selected_and_applied"
        )
        ordered = sorted(
            eligible_shown.items(),
            key=lambda item: (
                int(item[1]["context"].get("position") or 10_000),
                item[0],
            ),
        )
        for candidate_number, (candidate_id, item) in enumerate(ordered, start=1):
            context = item["context"]
            features = CandidateFeatures.model_validate(context["features"])
            if not features.hard_constraints_passed:
                raise ValueError(
                    "Recommendation-choice data cannot include candidates that failed hard checks."
                )
            selected_flag = candidate_id == selected_id
            rows.append(
                {
                    "dataset_schema_version": RECOMMENDATION_CHOICE_DATASET_SCHEMA_VERSION,
                    "decision_group_id": decision_group_id,
                    "candidate_number": candidate_number,
                    **features.model_dump(),
                    "ranker_id": context.get("ranker_id"),
                    "ranker_version": context.get("ranker_version"),
                    "rank_score": context.get("rank_score"),
                    "display_position": context.get("position"),
                    "choice_label": 1 if selected_flag else 0,
                    "choice_outcome": "selected" if selected_flag else "not_selected",
                    "selected_candidate_final_outcome": (
                        final_selected_outcome if selected_flag else ""
                    ),
                    "shown_at": _serialize_timestamp(item["created_at"]),
                }
            )

    return {
        "dataset_schema_version": RECOMMENDATION_CHOICE_DATASET_SCHEMA_VERSION,
        "feature_schema_version": "1.0",
        "decision_group_count": complete_group_count,
        "candidate_row_count": len(rows),
        "rows": rows,
        "important_note": (
            "This export contains only PII-free candidate feature snapshots from observed "
            "coordinator recommendation impressions with an applied choice. SAFE and "
            "CONDITIONALLY_SAFE alternatives are included; hard-rejected and "
            "INSUFFICIENT_DATA candidates are excluded from ranking labels."
        ),
    }


def recommendation_choice_dataset_to_csv(dataset: dict) -> str:
    rows = dataset["rows"]
    if not rows:
        return ""
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
