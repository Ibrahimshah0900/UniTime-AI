from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import TimetableEntry
from backend.multi_step_execution_service import (
    _determine_execution_status,
    _extract_error_message,
)
from backend.optimizer_execution_history import (
    OptimizerExecution,
    OptimizerExecutionStep,
    create_execution,
    finalize_execution,
    get_execution,
    get_execution_steps,
    link_execution_step,
)
from backend.optimizer_execution_reader import (
    get_optimizer_execution_detail,
    list_optimizer_executions,
)
from backend.optimizer_execution_rollback import (
    redo_optimizer_execution,
    undo_optimizer_execution,
)
from backend.student_resolution_applier import (
    StudentScheduleChange,
)


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Session:
    """
    Create a completely isolated in-memory database.

    These tests never touch the real UniTime-AI SQLite database.
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )

    Base.metadata.create_all(
        engine,
    )

    TestSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = TestSession()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def snapshot(
    *,
    risk_cost: int = 460,
    risks: int = 50,
    groups: int = 34,
    clashes: int = 0,
) -> dict:
    return {
        "entries": 181,
        "student_risk_cost": risk_cost,
        "student_groups": groups,
        "student_risks": {
            "total": risks,
            "confirmed": 0,
            "probable": risks,
            "possible": 0,
        },
        "clashes": {
            "total": clashes,
            "room": 0,
            "faculty": 0,
            "other": 0,
        },
    }


def add_timetable_entry(
    db: Session,
    *,
    entry_id: int,
    course_code: str,
) -> TimetableEntry:
    entry = TimetableEntry(
        id=entry_id,
        entry_kind="course",
        course_code=course_code,
        course_name="Test Course",
        semester=None,
        section="A",
        faculty="Test Faculty",
        room="TEST ROOM",
        day="Monday",
        start_time="08:30",
        end_time="10:00",
        class_type="lecture",
        raw_text=None,
        source="test",
    )

    db.add(
        entry
    )

    db.flush()

    return entry


def add_student_change(
    db: Session,
    *,
    entry_id: int,
    undone: bool = False,
) -> StudentScheduleChange:
    change = StudentScheduleChange(
        entry_id=entry_id,
        group_id=1,
        change_type="multi_step_optimizer_move",
        old_day="Monday",
        old_start_time="08:30",
        old_end_time="10:00",
        new_day="Tuesday",
        new_start_time="10:00",
        new_end_time="11:30",
        score=90.0,
        reasons_json="[]",
        risk_cost_before=460,
        risk_cost_after=440,
        total_risks_before=50,
        total_risks_after=48,
        undone=undone,
    )

    db.add(
        change
    )

    db.flush()

    return change


def create_grouped_execution(
    db: Session,
    *,
    execution_id: str = "execution_test",
    change_count: int = 2,
    changes_undone: bool = False,
) -> tuple[
    OptimizerExecution,
    list[StudentScheduleChange],
]:
    execution = create_execution(
        db,
        execution_id=execution_id,
        requested_steps=change_count,
        baseline=snapshot(),
    )

    changes = []

    for index in range(
        1,
        change_count + 1,
    ):
        add_timetable_entry(
            db,
            entry_id=index,
            course_code=f"CS{index:03d}",
        )

        change = add_student_change(
            db,
            entry_id=index,
            undone=changes_undone,
        )

        changes.append(
            change
        )

        link_execution_step(
            db,
            execution_id=execution_id,
            step_number=index,
            change_id=change.id,
        )

    finalize_execution(
        db,
        execution_id=execution_id,
        applied_steps=change_count,
        final_snapshot=snapshot(
            risk_cost=420,
            risks=46,
            groups=34,
            clashes=0,
        ),
        status=(
            "undone"
            if changes_undone
            else "completed"
        ),
        stop_reason="Test execution.",
    )

    db.commit()

    return execution, changes


# ---------------------------------------------------------------------------
# EXECUTION HISTORY MODEL / HELPERS
# ---------------------------------------------------------------------------


def test_create_execution_stores_baseline(
    db: Session,
):
    execution = create_execution(
        db,
        execution_id="history_1",
        requested_steps=3,
        baseline=snapshot(),
    )

    assert execution.execution_id == "history_1"
    assert execution.requested_steps == 3
    assert execution.applied_steps == 0
    assert execution.status == "running"

    assert execution.baseline_risk_cost == 460
    assert execution.final_risk_cost == 460

    assert execution.baseline_total_risks == 50
    assert execution.final_total_risks == 50

    assert execution.baseline_student_groups == 34
    assert execution.final_student_groups == 34

    assert execution.baseline_clashes == 0
    assert execution.final_clashes == 0


def test_duplicate_execution_id_is_rejected(
    db: Session,
):
    create_execution(
        db,
        execution_id="duplicate_test",
        requested_steps=1,
        baseline=snapshot(),
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        create_execution(
            db,
            execution_id="duplicate_test",
            requested_steps=1,
            baseline=snapshot(),
        )


def test_execution_steps_are_returned_in_step_order(
    db: Session,
):
    create_execution(
        db,
        execution_id="ordered_steps",
        requested_steps=3,
        baseline=snapshot(),
    )

    link_execution_step(
        db,
        execution_id="ordered_steps",
        step_number=3,
        change_id=103,
    )

    link_execution_step(
        db,
        execution_id="ordered_steps",
        step_number=1,
        change_id=101,
    )

    link_execution_step(
        db,
        execution_id="ordered_steps",
        step_number=2,
        change_id=102,
    )

    steps = get_execution_steps(
        db,
        "ordered_steps",
    )

    assert [
        step.step_number
        for step in steps
    ] == [
        1,
        2,
        3,
    ]

    assert [
        step.change_id
        for step in steps
    ] == [
        101,
        102,
        103,
    ]


def test_finalize_execution_updates_metrics(
    db: Session,
):
    create_execution(
        db,
        execution_id="finalize_test",
        requested_steps=3,
        baseline=snapshot(),
    )

    execution = finalize_execution(
        db,
        execution_id="finalize_test",
        applied_steps=2,
        final_snapshot=snapshot(
            risk_cost=420,
            risks=46,
            groups=33,
            clashes=0,
        ),
        status="partial",
        stop_reason="Stopped safely.",
        error_message="Third move rejected.",
    )

    assert execution.status == "partial"
    assert execution.applied_steps == 2

    assert execution.final_risk_cost == 420
    assert execution.final_total_risks == 46
    assert execution.final_student_groups == 33
    assert execution.final_clashes == 0

    assert execution.stop_reason == "Stopped safely."
    assert execution.error_message == "Third move rejected."

    assert execution.completed_at is not None


def test_get_execution_returns_none_when_missing(
    db: Session,
):
    result = get_execution(
        db,
        "does_not_exist",
    )

    assert result is None


# ---------------------------------------------------------------------------
# EXECUTION HISTORY READER
# ---------------------------------------------------------------------------


def test_execution_reader_lists_newest_first(
    db: Session,
):
    create_execution(
        db,
        execution_id="first",
        requested_steps=1,
        baseline=snapshot(),
    )

    create_execution(
        db,
        execution_id="second",
        requested_steps=1,
        baseline=snapshot(),
    )

    db.commit()

    executions = list_optimizer_executions(
        db
    )

    assert len(executions) == 2

    assert executions[0][
        "execution_id"
    ] == "second"

    assert executions[1][
        "execution_id"
    ] == "first"


def test_execution_detail_contains_linked_steps(
    db: Session,
):
    _, changes = create_grouped_execution(
        db,
        execution_id="detail_test",
        change_count=2,
    )

    detail = get_optimizer_execution_detail(
        db,
        execution_id="detail_test",
    )

    assert detail[
        "execution_id"
    ] == "detail_test"

    assert detail[
        "status"
    ] == "completed"

    assert detail[
        "steps"
    ] == [
        {
            "step_number": 1,
            "change_id": changes[0].id,
        },
        {
            "step_number": 2,
            "change_id": changes[1].id,
        },
    ]


def test_execution_detail_rejects_missing_execution(
    db: Session,
):
    with pytest.raises(
        ValueError,
        match="not found",
    ):
        get_optimizer_execution_detail(
            db,
            execution_id="missing",
        )


# ---------------------------------------------------------------------------
# EXECUTION SERVICE STATUS HELPERS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "result",
        "expected",
    ),
    [
        (
            {
                "applied_steps": 0,
                "failed_step": None,
            },
            "no_change",
        ),
        (
            {
                "applied_steps": 2,
                "failed_step": {
                    "step": 3,
                },
            },
            "partial",
        ),
        (
            {
                "applied_steps": 3,
                "failed_step": None,
            },
            "completed",
        ),
    ],
)
def test_determine_execution_status(
    result: dict,
    expected: str,
):
    assert (
        _determine_execution_status(
            result
        )
        == expected
    )


def test_extract_error_message_supports_direct_error():
    result = {
        "error_message": "Direct failure.",
    }

    assert (
        _extract_error_message(
            result
        )
        == "Direct failure."
    )


def test_extract_error_message_supports_failed_step():
    result = {
        "failed_step": {
            "error": (
                "Move rejected because it "
                "increases conflict groups."
            )
        }
    }

    assert (
        _extract_error_message(
            result
        )
        == (
            "Move rejected because it "
            "increases conflict groups."
        )
    )


def test_extract_error_message_returns_none_without_failure():
    assert (
        _extract_error_message(
            {
                "failed_step": None,
            }
        )
        is None
    )


# ---------------------------------------------------------------------------
# GROUPED UNDO
# ---------------------------------------------------------------------------


def test_grouped_undo_uses_reverse_step_order(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    _, changes = create_grouped_execution(
        db,
        execution_id="undo_order",
        change_count=3,
    )

    call_order = []

    def fake_undo(
        session: Session,
        *,
        change_id: int,
    ) -> dict:
        change = session.scalar(
            select(
                StudentScheduleChange
            ).where(
                StudentScheduleChange.id
                == change_id
            )
        )

        assert change is not None

        call_order.append(
            change_id
        )

        change.undone = True

        session.flush()

        return {
            "success": True,
            "change_id": change_id,
        }

    monkeypatch.setattr(
        "backend.optimizer_execution_rollback."
        "undo_student_resolution",
        fake_undo,
    )

    result = undo_optimizer_execution(
        db,
        execution_id="undo_order",
    )

    expected_order = [
        changes[2].id,
        changes[1].id,
        changes[0].id,
    ]

    assert call_order == expected_order
    assert result["status"] == "undone"
    assert result["undone_steps"] == 3

    execution = get_execution(
        db,
        "undo_order",
    )

    assert execution is not None
    assert execution.status == "undone"

    for change in changes:
        db.refresh(
            change
        )

        assert change.undone is True


def test_grouped_undo_rejects_fully_undone_execution(
    db: Session,
):
    create_grouped_execution(
        db,
        execution_id="already_undone",
        change_count=2,
        changes_undone=True,
    )

    with pytest.raises(
        ValueError,
        match="already fully undone",
    ):
        undo_optimizer_execution(
            db,
            execution_id="already_undone",
        )


# ---------------------------------------------------------------------------
# GROUPED REDO
# ---------------------------------------------------------------------------


def test_grouped_redo_uses_original_step_order(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    _, changes = create_grouped_execution(
        db,
        execution_id="redo_order",
        change_count=3,
        changes_undone=True,
    )

    call_order = []

    def fake_redo(
        session: Session,
        *,
        change_id: int,
    ) -> dict:
        change = session.scalar(
            select(
                StudentScheduleChange
            ).where(
                StudentScheduleChange.id
                == change_id
            )
        )

        assert change is not None

        call_order.append(
            change_id
        )

        change.undone = False

        session.flush()

        return {
            "success": True,
            "change_id": change_id,
        }

    monkeypatch.setattr(
        "backend.optimizer_execution_rollback."
        "redo_student_resolution",
        fake_redo,
    )

    result = redo_optimizer_execution(
        db,
        execution_id="redo_order",
    )

    expected_order = [
        changes[0].id,
        changes[1].id,
        changes[2].id,
    ]

    assert call_order == expected_order
    assert result["status"] == "completed"
    assert result["redone_steps"] == 3

    execution = get_execution(
        db,
        "redo_order",
    )

    assert execution is not None
    assert execution.status == "completed"

    for change in changes:
        db.refresh(
            change
        )

        assert change.undone is False


def test_grouped_redo_rejects_fully_active_execution(
    db: Session,
):
    create_grouped_execution(
        db,
        execution_id="already_active",
        change_count=2,
        changes_undone=False,
    )

    with pytest.raises(
        ValueError,
        match="already fully active",
    ):
        redo_optimizer_execution(
            db,
            execution_id="already_active",
        )


# ---------------------------------------------------------------------------
# DATABASE ISOLATION / LINK INTEGRITY
# ---------------------------------------------------------------------------


def test_execution_step_links_are_persisted(
    db: Session,
):
    _, changes = create_grouped_execution(
        db,
        execution_id="link_integrity",
        change_count=2,
    )

    links = list(
        db.scalars(
            select(
                OptimizerExecutionStep
            )
            .where(
                OptimizerExecutionStep.execution_id
                == "link_integrity"
            )
            .order_by(
                OptimizerExecutionStep.step_number
            )
        ).all()
    )

    assert len(links) == 2

    assert links[0].change_id == changes[0].id
    assert links[1].change_id == changes[1].id