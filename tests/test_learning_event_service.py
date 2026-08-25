from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.learning_event_service import record_learning_event, stable_learning_key
from backend.learning_event_export import (
    domain_learning_events_csv,
    export_domain_learning_events,
)
from backend.models import AcademicTerm, LearningEvent


def create_test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_learning_event_keys_are_stable_pseudonymous_and_namespaced():
    first = stable_learning_key("student", 42)
    assert first == stable_learning_key("student", 42)
    assert first != stable_learning_key("student", 43)
    assert first != stable_learning_key("clash_report", 42)
    assert len(first) == 64
    assert first != "42"
    assert "student" not in first


def test_learning_event_context_rejects_direct_and_nested_pii_keys():
    Session = create_test_session()
    with Session() as db:
        for context in (
            {"student_email": "student@example.edu"},
            {"nested": {"registration_number": "FA23-BAI-042"}},
            {"items": [{"full_name": "Student Name"}]},
        ):
            with pytest.raises(ValueError, match="forbidden PII key"):
                record_learning_event(
                    db,
                    event_type="student_enrolled",
                    entity_type="enrollment",
                    entity_key=stable_learning_key("enrollment", 1),
                    context=context,
                )
        assert list(db.scalars(select(LearningEvent)).all()) == []


def test_learning_event_is_append_only_structured_and_pii_free():
    Session = create_test_session()
    with Session() as db:
        term = AcademicTerm(code="FALL-2026", name="Fall 2026", status="active")
        db.add(term)
        db.flush()
        event = record_learning_event(
            db,
            term_id=term.id,
            event_type="student_enrolled",
            subject_key=stable_learning_key("student", 7),
            entity_type="enrollment",
            entity_key=stable_learning_key("enrollment", 9),
            actor_role="student",
            outcome_label="conflict_detected",
            context={
                "course_code": "CS-210",
                "section": "A",
                "conflict_count": 1,
            },
        )
        db.commit()
        db.refresh(event)

        assert event.context_schema_version == "1.0"
        assert json.loads(event.context_json) == {
            "conflict_count": 1,
            "course_code": "CS-210",
            "section": "A",
        }
        assert "example.edu" not in event.context_json
        assert event.subject_key == stable_learning_key("student", 7)

        dataset = export_domain_learning_events(db, term_id=term.id)
        assert dataset["contains_direct_pii"] is False
        assert dataset["event_count"] == 1
        assert dataset["events"][0]["context"] == {
            "conflict_count": 1,
            "course_code": "CS-210",
            "section": "A",
        }
        csv_export = domain_learning_events_csv(dataset)
        assert "student@example.edu" not in csv_export
        assert "conflict_detected" in csv_export
