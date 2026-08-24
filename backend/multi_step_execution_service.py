from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.global_optimizer import (
    build_timetable_snapshot,
)
from backend.multi_step_plan_applier import (
    DEFAULT_MAX_STEPS,
    apply_multi_step_optimization_plan,
)
from backend.optimizer_execution_history import (
    finalize_execution,
)
from backend.student_resolution_applier import (
    get_all_entries,
)


def _determine_execution_status(
    result: dict[str, Any],
) -> str:
    """
    Determine the plan-level status from the executor result.
    """

    applied_steps = int(
        result.get(
            "applied_steps",
            0,
        )
    )

    failed_step = result.get(
        "failed_step"
    )

    if applied_steps == 0:
        return "no_change"

    if failed_step is not None:
        return "partial"

    return "completed"


def _extract_error_message(
    result: dict[str, Any],
) -> str | None:
    """
    Extract a useful failure message without depending on
    one exact failed_step response shape.
    """

    direct_error = (
        result.get("error_message")
        or result.get("error")
    )

    if direct_error:
        return str(
            direct_error
        )

    failed_step = result.get(
        "failed_step"
    )

    if isinstance(
        failed_step,
        dict,
    ):
        message = (
            failed_step.get("error")
            or failed_step.get("message")
            or failed_step.get("reason")
        )

        if message:
            return str(
                message
            )

    return None


def apply_multi_step_plan_with_history(
    db: Session,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[str, Any]:
    """
    Execute the existing safe multi-step optimizer and then
    finalize its grouped execution-history record.

    Individual steps remain independently committed and
    undoable. This function adds plan-level completion state.
    """

    result = apply_multi_step_optimization_plan(
        db,
        max_steps=max_steps,
    )

    execution_id = result.get(
        "execution_id"
    )

    if not execution_id:
        raise ValueError(
            "Optimizer execution did not return an execution_id."
        )

    final_snapshot = build_timetable_snapshot(
        get_all_entries(
            db
        )
    )

    status = _determine_execution_status(
        result
    )

    applied_steps = int(
        result.get(
            "applied_steps",
            0,
        )
    )

    stop_reason = result.get(
        "stop_reason"
    )

    error_message = _extract_error_message(
        result
    )

    history = finalize_execution(
        db,
        execution_id=execution_id,
        applied_steps=applied_steps,
        final_snapshot=final_snapshot,
        status=status,
        stop_reason=(
            str(stop_reason)
            if stop_reason is not None
            else None
        ),
        error_message=error_message,
    )

    db.commit()

    result[
        "execution_history"
    ] = {
        "execution_id": (
            history.execution_id
        ),
        "status": (
            history.status
        ),
        "requested_steps": (
            history.requested_steps
        ),
        "applied_steps": (
            history.applied_steps
        ),
        "baseline_risk_cost": (
            history.baseline_risk_cost
        ),
        "final_risk_cost": (
            history.final_risk_cost
        ),
        "baseline_total_risks": (
            history.baseline_total_risks
        ),
        "final_total_risks": (
            history.final_total_risks
        ),
        "baseline_student_groups": (
            history.baseline_student_groups
        ),
        "final_student_groups": (
            history.final_student_groups
        ),
        "baseline_clashes": (
            history.baseline_clashes
        ),
        "final_clashes": (
            history.final_clashes
        ),
        "stop_reason": (
            history.stop_reason
        ),
        "error_message": (
            history.error_message
        ),
    }

    return result