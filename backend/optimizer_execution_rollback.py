from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.optimizer_execution_history import (
    OptimizerExecution,
    get_execution,
    get_execution_steps,
)
from backend.student_resolution_applier import (
    StudentScheduleChange,
    redo_student_resolution,
    undo_student_resolution,
)


def _get_change(
    db: Session,
    change_id: int,
) -> StudentScheduleChange:
    change = db.scalar(
        select(
            StudentScheduleChange
        ).where(
            StudentScheduleChange.id
            == change_id
        )
    )

    if change is None:
        raise ValueError(
            f"Student schedule change {change_id} was not found."
        )

    return change


def _require_execution(
    db: Session,
    execution_id: str,
) -> OptimizerExecution:
    execution = get_execution(
        db,
        execution_id,
    )

    if execution is None:
        raise ValueError(
            "Optimizer execution was not found."
        )

    return execution


def undo_optimizer_execution(
    db: Session,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """
    Undo every active timetable change belonging to one
    optimizer execution.

    Changes are undone in reverse step order because later
    optimizer steps were calculated on top of earlier ones.
    """

    execution = _require_execution(
        db,
        execution_id,
    )

    links = get_execution_steps(
        db,
        execution_id,
    )

    if not links:
        raise ValueError(
            "Optimizer execution contains no linked steps."
        )

    active_change_ids = []

    for link in links:
        change = _get_change(
            db,
            link.change_id,
        )

        if not change.undone:
            active_change_ids.append(
                change.id
            )

    if not active_change_ids:
        raise ValueError(
            "Optimizer execution is already fully undone."
        )

    results = []

    # Reverse order is required for safe rollback of a
    # sequential optimization plan.
    for link in reversed(
        links
    ):
        change = _get_change(
            db,
            link.change_id,
        )

        if change.undone:
            continue

        result = undo_student_resolution(
            db,
            change_id=change.id,
        )

        results.append(
            {
                "step_number": (
                    link.step_number
                ),
                "change_id": (
                    change.id
                ),
                "result": result,
            }
        )

    execution.status = "undone"
    execution.stop_reason = (
        "Optimizer execution undone as a grouped plan."
    )

    db.commit()

    return {
        "success": True,
        "execution_id": execution_id,
        "status": "undone",
        "undone_steps": len(
            results
        ),
        "changes": results,
    }


def redo_optimizer_execution(
    db: Session,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """
    Redo every undone timetable change belonging to one
    optimizer execution.

    Changes are replayed in original step order.
    """

    execution = _require_execution(
        db,
        execution_id,
    )

    links = get_execution_steps(
        db,
        execution_id,
    )

    if not links:
        raise ValueError(
            "Optimizer execution contains no linked steps."
        )

    undone_change_ids = []

    for link in links:
        change = _get_change(
            db,
            link.change_id,
        )

        if change.undone:
            undone_change_ids.append(
                change.id
            )

    if not undone_change_ids:
        raise ValueError(
            "Optimizer execution is already fully active."
        )

    results = []

    # Redo in original execution order.
    for link in links:
        change = _get_change(
            db,
            link.change_id,
        )

        if not change.undone:
            continue

        result = redo_student_resolution(
            db,
            change_id=change.id,
        )

        results.append(
            {
                "step_number": (
                    link.step_number
                ),
                "change_id": (
                    change.id
                ),
                "result": result,
            }
        )

    execution.status = "completed"
    execution.stop_reason = (
        "Optimizer execution redone as a grouped plan."
    )

    execution.completed_at = (
        datetime.now(UTC).replace(tzinfo=None)
    )

    db.commit()

    return {
        "success": True,
        "execution_id": execution_id,
        "status": "completed",
        "redone_steps": len(
            results
        ),
        "changes": results,
    }