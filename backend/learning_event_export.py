from __future__ import annotations

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import LearningEvent


DOMAIN_EVENT_DATASET_SCHEMA_VERSION = "1.0"


def export_domain_learning_events(
    db: Session,
    *,
    term_id: int | None = None,
) -> dict:
    statement = select(LearningEvent)
    if term_id is not None:
        statement = statement.where(LearningEvent.term_id == term_id)
    events = list(
        db.scalars(statement.order_by(LearningEvent.created_at, LearningEvent.id)).all()
    )
    return {
        "dataset_schema_version": DOMAIN_EVENT_DATASET_SCHEMA_VERSION,
        "contains_direct_pii": False,
        "event_count": len(events),
        "events": [
            {
                "event_id": event.id,
                "term_id": event.term_id,
                "event_type": event.event_type,
                "subject_key": event.subject_key,
                "entity_type": event.entity_type,
                "entity_key": event.entity_key,
                "actor_role": event.actor_role,
                "source": event.source,
                "outcome_label": event.outcome_label,
                "context_schema_version": event.context_schema_version,
                "context": json.loads(event.context_json),
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


def domain_learning_events_csv(dataset: dict) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "event_id",
        "term_id",
        "event_type",
        "subject_key",
        "entity_type",
        "entity_key",
        "actor_role",
        "source",
        "outcome_label",
        "context_schema_version",
        "context_json",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for event in dataset["events"]:
        row = dict(event)
        row["context_json"] = json.dumps(
            row.pop("context"),
            sort_keys=True,
            separators=(",", ":"),
        )
        writer.writerow(row)
    return output.getvalue()
