from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from backend.models import LearningEvent


LEARNING_CONTEXT_SCHEMA_VERSION = "1.0"
ALLOWED_LEARNING_EVENT_TYPES = frozenset(
    {
        "recommendation_generated",
        "recommendation_shown",
        "recommendation_selected",
        "recommendation_rejected",
        "resolution_applied",
        "resolution_undone",
        "resolution_redone",
        "manual_timetable_change",
        "student_enrolled",
        "student_dropped",
        "clash_report_submitted",
        "clash_report_verified",
        "clash_report_invalid",
        "clash_report_duplicate",
        "term_archived",
    }
)
ALLOWED_ACTOR_ROLES = frozenset(
    {"student", "faculty", "coordinator", "admin", "system"}
)
FORBIDDEN_CONTEXT_KEYS = frozenset(
    {
        "actor_user_id",
        "email",
        "full_name",
        "password",
        "password_hash",
        "registration_number",
        "student_email",
        "student_name",
        "student_user_id",
        "temporary_password",
        "user_id",
    }
)


def stable_learning_key(namespace: str, identifier: int | str) -> str:
    normalized_namespace = namespace.strip().lower()
    if not normalized_namespace:
        raise ValueError("Learning-event key namespace is required.")
    return hashlib.sha256(
        f"unitime-ai:{normalized_namespace}:{identifier}".encode("utf-8")
    ).hexdigest()


def _reject_pii_keys(value: Any, *, path: str = "context") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in FORBIDDEN_CONTEXT_KEYS:
                raise ValueError(
                    f"Learning-event {path} contains forbidden PII key {key!r}."
                )
            _reject_pii_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, nested in enumerate(value):
            _reject_pii_keys(nested, path=f"{path}[{index}]")


def record_learning_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_key: str,
    term_id: int | None = None,
    subject_key: str | None = None,
    actor_role: str | None = None,
    source: str = "backend",
    outcome_label: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> LearningEvent:
    if event_type not in ALLOWED_LEARNING_EVENT_TYPES:
        raise ValueError(f"Unsupported learning event type: {event_type}.")
    normalized_entity_type = entity_type.strip()
    normalized_entity_key = entity_key.strip()
    normalized_source = source.strip()
    if not normalized_entity_type or len(normalized_entity_type) > 40:
        raise ValueError("entity_type must contain 1-40 characters.")
    if not normalized_entity_key or len(normalized_entity_key) > 64:
        raise ValueError("entity_key must contain 1-64 characters.")
    if not normalized_source or len(normalized_source) > 40:
        raise ValueError("source must contain 1-40 characters.")
    if subject_key is not None and len(subject_key) != 64:
        raise ValueError("subject_key must be a 64-character stable pseudonymous key.")
    if actor_role is not None and actor_role not in ALLOWED_ACTOR_ROLES:
        raise ValueError(f"Unsupported actor role: {actor_role}.")
    if outcome_label is not None and len(outcome_label) > 50:
        raise ValueError("outcome_label must contain at most 50 characters.")

    selected_context = dict(context or {})
    _reject_pii_keys(selected_context)
    context_json = json.dumps(
        selected_context,
        sort_keys=True,
        separators=(",", ":"),
    )
    event = LearningEvent(
        term_id=term_id,
        event_type=event_type,
        subject_key=subject_key,
        entity_type=normalized_entity_type,
        entity_key=normalized_entity_key,
        actor_role=actor_role,
        source=normalized_source,
        outcome_label=outcome_label,
        context_schema_version=LEARNING_CONTEXT_SCHEMA_VERSION,
        context_json=context_json,
    )
    db.add(event)
    return event
