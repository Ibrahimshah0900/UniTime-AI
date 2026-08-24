from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.global_optimizer import (
    build_timetable_snapshot,
    optimize_timetable_globally,
)
from backend.models import TimetableEntry
from backend.multi_step_optimizer import (
    MAX_ALLOWED_STEPS as PLANNER_MAX_STEPS,
    build_multi_step_optimization_plan,
)
from backend.multi_step_plan_applier import (
    MAX_ALLOWED_STEPS as EXECUTOR_MAX_STEPS,
    apply_multi_step_optimization_plan,
)


# ---------------------------------------------------------------------------
# TEST HELPERS
# ---------------------------------------------------------------------------


def seed_entries(Session) -> None:
    with Session() as db:
        db.add_all(
            [
                TimetableEntry(
                    course_code="CS-101",
                    course_name="Programming Fundamentals",
                    semester="Fall 2026",
                    section="A",
                    faculty="Dr Ada",
                    room="C-101",
                    day="Monday",
                    start_time="09:00",
                    end_time="10:00",
                ),
                TimetableEntry(
                    course_code="MTH-101",
                    course_name="Calculus",
                    semester="Fall 2026",
                    section="A",
                    faculty="Dr Euler",
                    room="C-102",
                    day="Monday",
                    start_time="09:30",
                    end_time="10:30",
                ),
                TimetableEntry(
                    course_code="CS-201",
                    course_name="Data Structures",
                    semester="Fall 2026",
                    section="A",
                    faculty="Dr Ada",
                    room="C-101",
                    day="Tuesday",
                    start_time="10:00",
                    end_time="11:00",
                ),
                TimetableEntry(
                    course_code="PHY-101",
                    course_name="Physics",
                    semester="Fall 2026",
                    section="B",
                    faculty="Dr Curie",
                    room="LAB-1",
                    day="Wednesday",
                    start_time="11:00",
                    end_time="12:00",
                    class_type="lab",
                ),
            ]
        )
        db.commit()


@pytest.fixture
def test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed_entries(Session)
    yield Session


def load_entries(test_session) -> list[TimetableEntry]:
    """
    Load the current timetable in read-only form for optimizer tests.

    None of the normal optimizer/planner tests below commit database
    changes.
    """

    db = test_session()

    try:
        statement = (
            select(TimetableEntry)
            .order_by(TimetableEntry.id)
        )

        return list(
            db.scalars(statement).all()
        )

    finally:
        db.close()


# ---------------------------------------------------------------------------
# BASELINE
# ---------------------------------------------------------------------------


def test_timetable_has_entries(test_session):
    entries = load_entries(test_session)

    assert len(entries) > 0


def test_baseline_snapshot_is_valid(test_session):
    entries = load_entries(test_session)

    snapshot = build_timetable_snapshot(
        entries
    )

    assert snapshot["entries"] == len(entries)

    assert (
        snapshot["student_risk_cost"]
        >= 0
    )

    assert (
        snapshot["student_groups"]
        >= 0
    )

    assert (
        snapshot["clashes"]["total"]
        >= 0
    )

    assert (
        snapshot["student_risks"]["total"]
        >= 0
    )


# ---------------------------------------------------------------------------
# GLOBAL OPTIMIZER SAFETY
# ---------------------------------------------------------------------------


def test_global_optimizer_is_read_only(test_session):
    entries = load_entries(test_session)

    before = [
        (
            entry.id,
            entry.day,
            entry.start_time,
            entry.end_time,
            entry.room,
        )
        for entry in entries
    ]

    optimize_timetable_globally(
        entries,
        limit=10,
    )

    after = [
        (
            entry.id,
            entry.day,
            entry.start_time,
            entry.end_time,
            entry.room,
        )
        for entry in entries
    ]

    assert before == after


def test_global_optimizer_returns_only_safe_moves(test_session):
    entries = load_entries(test_session)

    result = optimize_timetable_globally(
        entries,
        limit=100,
    )

    baseline = result["baseline"]

    for move in result[
        "ranked_moves"
    ]:
        improvement = move[
            "improvement"
        ]

        risk_cost = improvement[
            "student_risk_cost"
        ]

        student_groups = improvement[
            "student_groups"
        ]

        general_clashes = improvement[
            "general_clashes"
        ]

        # Every returned move must improve
        # overall student/cohort risk.
        assert (
            risk_cost["after"]
            < risk_cost["before"]
        )

        assert (
            risk_cost["reduction"]
            > 0
        )

        # Global optimizer must never return a
        # move that increases conflict groups.
        assert (
            student_groups["after"]
            <= student_groups["before"]
        )

        # General timetable clashes must never
        # increase.
        assert (
            general_clashes["after"]
            <= general_clashes["before"]
        )

        # The live timetable currently has no
        # general clashes. Returned candidates
        # therefore should preserve that state.
        if (
            baseline[
                "clashes"
            ][
                "total"
            ]
            == 0
        ):
            assert (
                general_clashes["after"]
                == 0
            )


def test_global_optimizer_candidate_accounting(test_session):
    entries = load_entries(test_session)

    result = optimize_timetable_globally(
        entries,
        limit=10,
    )

    summary = result[
        "candidate_summary"
    ]

    assert (
        summary["generated"]
        >= 0
    )

    assert (
        summary["globally_safe"]
        >= 0
    )

    assert (
        summary["rejected"]
        >= 0
    )

    assert (
        summary["globally_safe"]
        + summary["rejected"]
        == summary["generated"]
    )


def test_global_optimizer_best_move_matches_ranking(test_session):
    entries = load_entries(test_session)

    result = optimize_timetable_globally(
        entries,
        limit=10,
    )

    ranked = result[
        "ranked_moves"
    ]

    if not ranked:
        assert (
            result["best_move"]
            is None
        )

        return

    assert (
        result["best_move"]
        == ranked[0]
    )


# ---------------------------------------------------------------------------
# MULTI-STEP PLANNER SAFETY
# ---------------------------------------------------------------------------


def test_multi_step_planner_is_read_only(test_session):
    entries = load_entries(test_session)

    before = [
        (
            entry.id,
            entry.day,
            entry.start_time,
            entry.end_time,
            entry.room,
        )
        for entry in entries
    ]

    build_multi_step_optimization_plan(
        entries,
        max_steps=3,
    )

    after = [
        (
            entry.id,
            entry.day,
            entry.start_time,
            entry.end_time,
            entry.room,
        )
        for entry in entries
    ]

    assert before == after


def test_multi_step_plan_never_worsens_global_safety(test_session):
    entries = load_entries(test_session)

    result = (
        build_multi_step_optimization_plan(
            entries,
            max_steps=10,
        )
    )

    baseline = result[
        "baseline"
    ]

    projected = result[
        "projected_final"
    ]

    # Risk cost cannot worsen.
    assert (
        projected[
            "student_risk_cost"
        ]
        <= baseline[
            "student_risk_cost"
        ]
    )

    # Student conflict groups cannot increase.
    assert (
        projected[
            "student_groups"
        ]
        <= baseline[
            "student_groups"
        ]
    )

    # General clashes cannot increase.
    assert (
        projected[
            "clashes"
        ][
            "total"
        ]
        <= baseline[
            "clashes"
        ][
            "total"
        ]
    )

    # Confirmed student risks cannot increase.
    assert (
        projected[
            "student_risks"
        ][
            "confirmed"
        ]
        <= baseline[
            "student_risks"
        ][
            "confirmed"
        ]
    )


def test_every_planner_step_is_monotonically_safe(test_session):
    entries = load_entries(test_session)

    result = (
        build_multi_step_optimization_plan(
            entries,
            max_steps=10,
        )
    )

    steps = result[
        "steps"
    ]

    for step in steps:
        improvement = step[
            "improvement"
        ]

        risk_cost = improvement[
            "student_risk_cost"
        ]

        groups = improvement[
            "student_groups"
        ]

        clashes = improvement[
            "general_clashes"
        ]

        assert (
            risk_cost["after"]
            < risk_cost["before"]
        )

        assert (
            groups["after"]
            <= groups["before"]
        )

        assert (
            clashes["after"]
            <= clashes["before"]
        )


def test_planner_does_not_move_same_entry_twice(test_session):
    entries = load_entries(test_session)

    result = (
        build_multi_step_optimization_plan(
            entries,
            max_steps=10,
        )
    )

    entry_ids = [
        step["entry_id"]
        for step in result[
            "steps"
        ]
    ]

    assert (
        len(entry_ids)
        == len(set(entry_ids))
    )


def test_planner_step_count_is_bounded(test_session):
    entries = load_entries(test_session)

    requested = 5

    result = (
        build_multi_step_optimization_plan(
            entries,
            max_steps=requested,
        )
    )

    assert (
        result["planned_steps"]
        <= requested
    )

    assert (
        len(result["steps"])
        == result["planned_steps"]
    )


# ---------------------------------------------------------------------------
# INVALID INPUT PROTECTION
# ---------------------------------------------------------------------------


def test_planner_rejects_zero_steps(test_session):
    entries = load_entries(test_session)

    with pytest.raises(
        ValueError,
        match="max_steps must be at least 1",
    ):
        build_multi_step_optimization_plan(
            entries,
            max_steps=0,
        )


def test_planner_rejects_excessive_steps(test_session):
    entries = load_entries(test_session)

    with pytest.raises(
        ValueError,
        match="max_steps cannot exceed",
    ):
        build_multi_step_optimization_plan(
            entries,
            max_steps=(
                PLANNER_MAX_STEPS
                + 1
            ),
        )


def test_executor_rejects_zero_steps_without_writing(test_session):
    """
    This exercises executor input protection only.

    max_steps=0 fails before any timetable mutation or commit.
    """

    db = test_session()

    try:
        with pytest.raises(
            ValueError,
            match="max_steps must be at least 1",
        ):
            apply_multi_step_optimization_plan(
                db,
                max_steps=0,
            )

    finally:
        db.rollback()
        db.close()


def test_executor_rejects_excessive_steps_without_writing(test_session):
    """
    This also fails before execution begins, so it is safe
    against the current database.
    """

    db = test_session()

    try:
        with pytest.raises(
            ValueError,
            match="max_steps cannot exceed",
        ):
            apply_multi_step_optimization_plan(
                db,
                max_steps=(
                    EXECUTOR_MAX_STEPS
                    + 1
                ),
            )

    finally:
        db.rollback()
        db.close()
