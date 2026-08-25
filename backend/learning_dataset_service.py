from __future__ import annotations

from collections import Counter, defaultdict
import csv
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.candidate_ranker import CandidateFeatures
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
