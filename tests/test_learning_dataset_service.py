from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.candidate_ranker import CandidateFeatures
from backend.database import Base
from backend.learning_dataset_service import (
    build_ranker_dataset,
    ranker_dataset_to_csv,
)
from backend.models import AcademicTerm, TimetableEntry
from backend.student_resolution_applier import (
    ResolutionLearningEvent,
    StudentScheduleChange,
)


def create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_change(db) -> StudentScheduleChange:
    db.add(AcademicTerm(code="FALL-2026", name="Fall 2026", status="active"))
    entry = TimetableEntry(
        term_id=1,
        course_code="AI-301",
        day="Monday",
        start_time="10:00",
        end_time="11:00",
    )
    db.add(entry)
    db.flush()
    change = StudentScheduleChange(
        term_id=1,
        entry_id=entry.id,
        group_id=None,
        change_type="clash_report_resolution",
        old_day="Monday",
        old_start_time="10:00",
        old_end_time="11:00",
        new_day="Tuesday",
        new_start_time="10:00",
        new_end_time="11:00",
        score=74,
        reasons_json="[]",
        risk_cost_before=100,
        risk_cost_after=0,
        total_risks_before=1,
        total_risks_after=0,
        undone=False,
    )
    db.add(change)
    db.flush()
    return change


def feature_json() -> str:
    return CandidateFeatures(
        safety_status="CONDITIONALLY_SAFE",
        duration_minutes=60,
        affected_students=12,
        confirmed_conflicts_removed=1,
        inferred_conflicts_removed=0,
        structural_clashes_removed=0,
        conflict_groups_removed=1,
        weighted_risk_reduction=100,
        day_distance=1,
        time_shift_minutes=0,
        late_slot=False,
        missing_metadata_count=2,
    ).model_dump_json()


def add_event(
    db,
    change: StudentScheduleChange,
    *,
    event_type: str,
    outcome_label: str,
    created_at: datetime,
) -> None:
    db.add(
        ResolutionLearningEvent(
            term_id=1,
            report_id=None,
            change_id=change.id,
            actor_user_id=None,
            candidate_id="0123456789abcdef01234567",
            event_type=event_type,
            outcome_label=outcome_label,
            ranker_id="deterministic_weighted",
            ranker_version="1.0",
            feature_schema_version="1.0",
            safety_status="CONDITIONALLY_SAFE",
            features_json=feature_json(),
            rank_score=74,
            created_at=created_at,
        )
    )


def test_dataset_uses_latest_append_only_outcome_and_omits_identifiers():
    Session = create_session()
    with Session() as db:
        change = seed_change(db)
        add_event(
            db,
            change,
            event_type="candidate_applied",
            outcome_label="accepted",
            created_at=datetime(2026, 1, 1, 10, 0),
        )
        add_event(
            db,
            change,
            event_type="resolution_undone",
            outcome_label="undone",
            created_at=datetime(2026, 1, 2, 10, 0),
        )
        add_event(
            db,
            change,
            event_type="resolution_redone",
            outcome_label="redone",
            created_at=datetime(2026, 1, 3, 10, 0),
        )
        db.commit()

        dataset = build_ranker_dataset(db)
        assert dataset["total_examples"] == 1
        assert dataset["label_counts"] == {"redone": 1}
        row = dataset["rows"][0]
        assert row["example_id"] == "example-000001"
        assert row["hard_constraints_passed"] is True
        assert row["outcome_label"] == "redone"
        assert row["outcome_event_count"] == 3
        assert row["affected_students"] == 12
        assert set(row).isdisjoint(
            {
                "term_id",
                "report_id",
                "change_id",
                "actor_user_id",
                "student_user_id",
                "registration_number",
                "email",
                "course_code",
                "section",
                "faculty",
            }
        )
        csv_output = ranker_dataset_to_csv(dataset)
        assert "outcome_label" in csv_output
        assert "redone" in csv_output
        assert "course_code" not in csv_output


def test_dataset_rejects_corrupt_history_without_single_application_event():
    Session = create_session()
    with Session() as db:
        change = seed_change(db)
        add_event(
            db,
            change,
            event_type="resolution_undone",
            outcome_label="undone",
            created_at=datetime(2026, 1, 1, 10, 0),
        )
        db.commit()

        with pytest.raises(ValueError, match="exactly one candidate_applied"):
            build_ranker_dataset(db)


def test_empty_dataset_has_no_csv_rows():
    Session = create_session()
    with Session() as db:
        assert build_ranker_dataset(db)["rows"] == []
        assert ranker_dataset_to_csv(build_ranker_dataset(db)) == ""
