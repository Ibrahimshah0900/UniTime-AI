from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.optimizer_execution_history import (
    OptimizerExecution,
    get_execution,
    get_execution_steps,
)


def serialize_execution(
    execution: OptimizerExecution,
) -> dict[str, Any]:
    return {
        "execution_id": execution.execution_id,
        "status": execution.status,
        "requested_steps": execution.requested_steps,
        "applied_steps": execution.applied_steps,
        "baseline": {
            "student_risk_cost": (
                execution.baseline_risk_cost
            ),
            "total_student_risks": (
                execution.baseline_total_risks
            ),
            "student_groups": (
                execution.baseline_student_groups
            ),
            "general_clashes": (
                execution.baseline_clashes
            ),
        },
        "final": {
            "student_risk_cost": (
                execution.final_risk_cost
            ),
            "total_student_risks": (
                execution.final_total_risks
            ),
            "student_groups": (
                execution.final_student_groups
            ),
            "general_clashes": (
                execution.final_clashes
            ),
        },
        "stop_reason": execution.stop_reason,
        "error_message": execution.error_message,
        "created_at": (
            execution.created_at.isoformat()
            if execution.created_at
            else None
        ),
        "completed_at": (
            execution.completed_at.isoformat()
            if execution.completed_at
            else None
        ),
    }


def list_optimizer_executions(
    db: Session,
) -> list[dict[str, Any]]:
    """
    Return all grouped optimizer executions,
    newest first.
    """

    statement = (
        select(
            OptimizerExecution
        )
        .order_by(
            OptimizerExecution.id.desc()
        )
    )

    executions = list(
        db.scalars(
            statement
        ).all()
    )

    return [
        serialize_execution(
            execution
        )
        for execution in executions
    ]


def get_optimizer_execution_detail(
    db: Session,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """
    Return one optimizer execution together with
    its linked change IDs.
    """

    execution = get_execution(
        db,
        execution_id,
    )

    if execution is None:
        raise ValueError(
            "Optimizer execution was not found."
        )

    links = get_execution_steps(
        db,
        execution_id,
    )

    result = serialize_execution(
        execution
    )

    result["steps"] = [
        {
            "step_number": link.step_number,
            "change_id": link.change_id,
        }
        for link in links
    ]

    return result