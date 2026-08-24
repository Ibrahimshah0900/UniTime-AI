from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.global_optimizer import (
    build_timetable_snapshot,
    calculate_student_risk_cost,
    optimize_timetable_globally,
)
from backend.models import TimetableEntry
from backend.optimizer_execution_history import (
    OptimizerExecution,
    OptimizerExecutionStep,
    create_execution,
    finalize_execution,
    get_execution_steps,
    link_execution_step,
)
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
)
from backend.student_conflict_groups import build_student_conflict_groups
from backend.student_resolution_applier import (
    StudentScheduleChange,
    get_all_entries,
    validate_specific_destination,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_MAX_STEPS = 5
MAX_ALLOWED_STEPS = 20


# ---------------------------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------------------------


def count_confirmed_risks(
    risks: list[dict],
) -> int:
    return sum(
        1
        for risk in risks
        if risk.get("risk_level") == "confirmed"
    )


def count_clash_types(
    clashes: list[dict],
) -> dict:
    room = sum(
        1
        for clash in clashes
        if clash.get("type") == "room"
    )

    faculty = sum(
        1
        for clash in clashes
        if clash.get("type") == "faculty"
    )

    other = (
        len(clashes)
        - room
        - faculty
    )

    return {
        "total": len(clashes),
        "room": room,
        "faculty": faculty,
        "other": other,
    }


def select_next_live_move(
    optimization_result: dict,
    *,
    moved_entry_ids: set[int],
) -> dict | None:
    """
    Select the highest-ranked live move whose entry has not already
    been moved during this multi-step execution.
    """

    for move in optimization_result.get(
        "ranked_moves",
        [],
    ):
        entry_id = move.get(
            "entry_id"
        )

        if entry_id is None:
            continue

        if entry_id in moved_entry_ids:
            continue

        if move.get(
            "room_status"
        ) not in {
            "available",
            "online",
        }:
            continue

        return move

    return None


def validate_entry_matches_move(
    entry: TimetableEntry,
    move: dict,
) -> None:
    move_from = move[
        "move_from"
    ]

    if (
        entry.day
        != move_from["day"]
        or entry.start_time
        != move_from["start_time"]
        or entry.end_time
        != move_from["end_time"]
    ):
        raise ValueError(
            "The timetable entry no longer matches "
            "the optimizer's expected source slot."
        )


# ---------------------------------------------------------------------------
# SAFETY VALIDATION
# ---------------------------------------------------------------------------


def validate_live_improvement(
    *,
    risks_before: list[dict],
    risks_after: list[dict],
    clashes_before: list[dict],
    clashes_after: list[dict],
) -> dict:
    risk_cost_before = (
        calculate_student_risk_cost(
            risks_before
        )
    )

    risk_cost_after = (
        calculate_student_risk_cost(
            risks_after
        )
    )

    confirmed_before = (
        count_confirmed_risks(
            risks_before
        )
    )

    confirmed_after = (
        count_confirmed_risks(
            risks_after
        )
    )

    groups_before = len(
        build_student_conflict_groups(
            risks_before
        )
    )

    groups_after = len(
        build_student_conflict_groups(
            risks_after
        )
    )

    if (
        groups_after
        > groups_before
    ):
        raise ValueError(
            "Move rejected because it increases "
            "student conflict groups."
        )

    if (
        risk_cost_after
        >= risk_cost_before
    ):
        raise ValueError(
            "Move rejected because global "
            "student/cohort risk did not decrease."
        )

    if (
        confirmed_after
        > confirmed_before
    ):
        raise ValueError(
            "Move rejected because it creates "
            "additional confirmed student conflicts."
        )

    if (
        len(clashes_after)
        > len(clashes_before)
    ):
        raise ValueError(
            "Move rejected because it creates "
            "additional general timetable clashes."
        )

    return {
        "risk_cost_before": (
            risk_cost_before
        ),
        "risk_cost_after": (
            risk_cost_after
        ),
        "risk_cost_reduction": (
            risk_cost_before
            - risk_cost_after
        ),
        "student_risks_before": len(
            risks_before
        ),
        "student_risks_after": len(
            risks_after
        ),
        "student_risks_reduction": (
            len(risks_before)
            - len(risks_after)
        ),
        "confirmed_before": (
            confirmed_before
        ),
        "confirmed_after": (
            confirmed_after
        ),
        "student_groups_before": (
            groups_before
        ),
        "student_groups_after": (
            groups_after
        ),
    }


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------


def create_multi_step_change_record(
    db: Session,
    *,
    execution_id: str,
    step_number: int,
    entry: TimetableEntry,
    move: dict,
    old_day: str,
    old_start_time: str,
    old_end_time: str,
    validation: dict,
) -> StudentScheduleChange:
    reasons = list(
        move.get(
            "reasons",
            [],
        )
    )

    # Store lightweight plan grouping information inside
    # the existing history payload until a dedicated plan
    # history table is introduced later.
    reasons.append(
        f"Multi-step execution ID: {execution_id}"
    )

    reasons.append(
        f"Multi-step execution step: {step_number}"
    )

    move_to = move[
        "move_to"
    ]

    change = StudentScheduleChange(
        entry_id=entry.id,
        group_id=move.get(
            "source_group_id",
            0,
        ),
        change_type=(
            "multi_step_optimizer_move"
        ),
        old_day=old_day,
        old_start_time=(
            old_start_time
        ),
        old_end_time=(
            old_end_time
        ),
        new_day=move_to[
            "day"
        ],
        new_start_time=(
            move_to[
                "start_time"
            ]
        ),
        new_end_time=(
            move_to[
                "end_time"
            ]
        ),
        score=float(
            move.get(
                "global_score",
                0,
            )
        ),
        reasons_json=json.dumps(
            reasons
        ),
        risk_cost_before=(
            validation[
                "risk_cost_before"
            ]
        ),
        risk_cost_after=(
            validation[
                "risk_cost_after"
            ]
        ),
        total_risks_before=(
            validation[
                "student_risks_before"
            ]
        ),
        total_risks_after=(
            validation[
                "student_risks_after"
            ]
        ),
        undone=False,
    )

    db.add(
        change
    )

    return change


# ---------------------------------------------------------------------------
# APPLY ONE LIVE STEP
# ---------------------------------------------------------------------------


def apply_one_live_step(
    db: Session,
    *,
    execution_id: str,
    step_number: int,
    move: dict,
) -> dict[str, Any]:
    """
    Apply one optimizer-selected move safely.

    This function commits exactly one timetable move.
    """

    entries_before = get_all_entries(
        db
    )

    entry = db.get(
        TimetableEntry,
        move[
            "entry_id"
        ],
    )

    if entry is None:
        raise ValueError(
            "The timetable entry selected by "
            "the optimizer no longer exists."
        )

    validate_entry_matches_move(
        entry,
        move,
    )

    move_to = move[
        "move_to"
    ]

    feasibility = (
        validate_specific_destination(
            entry,
            day=move_to[
                "day"
            ],
            start_time=move_to[
                "start_time"
            ],
            end_time=move_to[
                "end_time"
            ],
            entries=entries_before,
        )
    )

    risks_before = (
        analyze_student_conflicts(
            entries_before
        )
    )

    clashes_before = (
        detect_clashes(
            entries_before
        )
    )

    old_day = entry.day

    old_start_time = (
        entry.start_time
    )

    old_end_time = (
        entry.end_time
    )

    # ---------------------------------------------------------
    # PROVISIONAL MOVE
    # ---------------------------------------------------------

    entry.day = move_to[
        "day"
    ]

    entry.start_time = (
        move_to[
            "start_time"
        ]
    )

    entry.end_time = (
        move_to[
            "end_time"
        ]
    )

    db.flush()

    entries_after = get_all_entries(
        db
    )

    risks_after = (
        analyze_student_conflicts(
            entries_after
        )
    )

    clashes_after = (
        detect_clashes(
            entries_after
        )
    )

    validation = (
        validate_live_improvement(
            risks_before=(
                risks_before
            ),
            risks_after=(
                risks_after
            ),
            clashes_before=(
                clashes_before
            ),
            clashes_after=(
                clashes_after
            ),
        )
    )

    predicted_reduction = (
        move.get(
            "improvement",
            {},
        )
        .get(
            "student_risk_cost",
            {},
        )
        .get(
            "reduction"
        )
    )

    actual_reduction = (
        validation[
            "risk_cost_reduction"
        ]
    )

    history = (
        create_multi_step_change_record(
            db,
            execution_id=execution_id,
            step_number=step_number,
            entry=entry,
            move=move,
            old_day=old_day,
            old_start_time=(
                old_start_time
            ),
            old_end_time=(
                old_end_time
            ),
            validation=validation,
        )
    )

    db.flush()

    link_execution_step(
        db,
        execution_id=execution_id,
        step_number=step_number,
        change_id=history.id,
    )

    db.commit()

    db.refresh(
        entry
    )

    db.refresh(
        history
    )

    return {
        "step": step_number,
        "change_id": (
            history.id
        ),
        "entry_id": (
            entry.id
        ),
        "course_code": (
            entry.course_code
        ),
        "course_name": (
            entry.course_name
        ),
        "section": (
            entry.section
        ),
        "faculty": (
            entry.faculty
        ),
        "room": (
            entry.room
        ),
        "class_type": (
            entry.class_type
        ),
        "source_group_id": (
            move.get(
                "source_group_id"
            )
        ),
        "move_from": {
            "day": (
                old_day
            ),
            "start_time": (
                old_start_time
            ),
            "end_time": (
                old_end_time
            ),
        },
        "move_to": {
            "day": (
                entry.day
            ),
            "start_time": (
                entry.start_time
            ),
            "end_time": (
                entry.end_time
            ),
        },
        "local_score": (
            move.get(
                "local_score"
            )
        ),
        "global_score": (
            move.get(
                "global_score"
            )
        ),
        "faculty_available": (
            feasibility[
                "faculty_available"
            ]
        ),
        "room_status": (
            feasibility[
                "room_status"
            ]
        ),
        "room_available": (
            feasibility[
                "room_available"
            ]
        ),
        "validation": {
            "student_risk_cost": {
                "before": (
                    validation[
                        "risk_cost_before"
                    ]
                ),
                "after": (
                    validation[
                        "risk_cost_after"
                    ]
                ),
                "reduction": (
                    validation[
                        "risk_cost_reduction"
                    ]
                ),
            },
            "student_risks": {
                "before": (
                    validation[
                        "student_risks_before"
                    ]
                ),
                "after": (
                    validation[
                        "student_risks_after"
                    ]
                ),
                "reduction": (
                    validation[
                        "student_risks_reduction"
                    ]
                ),
            },
            "confirmed_risks": {
                "before": (
                    validation[
                        "confirmed_before"
                    ]
                ),
                "after": (
                    validation[
                        "confirmed_after"
                    ]
                ),
            },
            "general_clashes": {
                "before": (
                    count_clash_types(
                        clashes_before
                    )
                ),
                "after": (
                    count_clash_types(
                        clashes_after
                    )
                ),
            },
        },
        "optimizer_prediction": {
            "predicted_risk_cost_reduction": (
                predicted_reduction
            ),
            "actual_risk_cost_reduction": (
                actual_reduction
            ),
            "prediction_matches": (
                predicted_reduction
                == actual_reduction
            ),
        },
        "reasons": (
            move.get(
                "reasons",
                [],
            )
        ),
    }


# ---------------------------------------------------------------------------
# SAFE MULTI-STEP EXECUTION
# ---------------------------------------------------------------------------


def apply_multi_step_optimization_plan(
    db: Session,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[str, Any]:
    """
    Execute multiple globally beneficial timetable moves safely.

    IMPORTANT:

    This does NOT blindly apply a previously generated plan.

    Before every step it:

    1. Reloads the live timetable.
    2. Re-runs the global optimizer.
    3. Selects the current best unused timetable entry.
    4. Rechecks faculty and room availability.
    5. Applies the move provisionally.
    6. Recalculates all student risks.
    7. Recalculates all general clashes.
    8. Rejects unsafe changes.
    9. Commits that one safe step.
    10. Repeats from the newly committed timetable.

    If a later step fails, all earlier successful steps remain
    committed and fully undoable through their history records.
    """

    if max_steps < 1:
        raise ValueError(
            "max_steps must be at least 1."
        )

    if max_steps > MAX_ALLOWED_STEPS:
        raise ValueError(
            f"max_steps cannot exceed "
            f"{MAX_ALLOWED_STEPS}."
        )

    execution_id = (
        uuid4().hex
    )
    history_baseline = build_timetable_snapshot(
        get_all_entries(db)
    )

    create_execution(
        db,
        execution_id=execution_id,
        requested_steps=max_steps,
        baseline=history_baseline,
    )

    # Commit the plan-level record first so it survives
    # even when a later optimizer step fails safely.
    db.commit()

    initial_entries = get_all_entries(
        db
    )

    baseline = build_timetable_snapshot(
        initial_entries
    )

    moved_entry_ids: set[int] = set()

    applied_steps: list[
        dict
    ] = []

    stop_reason = (
        "Maximum requested steps reached."
    )

    failed_step: dict | None = None

    # ---------------------------------------------------------
    # SEQUENTIAL LIVE EXECUTION
    # ---------------------------------------------------------

    for requested_step in range(
        1,
        max_steps + 1,
    ):
        try:
            live_entries = (
                get_all_entries(
                    db
                )
            )

            optimization = (
                optimize_timetable_globally(
                    live_entries,
                    limit=100,
                )
            )

            if not optimization.get(
                "ranked_moves"
            ):
                stop_reason = (
                    "No further globally beneficial "
                    "moves are available."
                )
                break

            next_move = (
                select_next_live_move(
                    optimization,
                    moved_entry_ids=(
                        moved_entry_ids
                    ),
                )
            )

            if next_move is None:
                stop_reason = (
                    "No further globally beneficial "
                    "moves are available for entries "
                    "not already moved in this execution."
                )
                break

            step_result = (
                apply_one_live_step(
                    db,
                    execution_id=(
                        execution_id
                    ),
                    step_number=(
                        len(
                            applied_steps
                        )
                        + 1
                    ),
                    move=next_move,
                )
            )

            applied_steps.append(
                step_result
            )

            moved_entry_ids.add(
                next_move[
                    "entry_id"
                ]
            )

        except Exception as exc:
            db.rollback()

            failed_step = {
                "requested_step": (
                    requested_step
                ),
                "error": str(
                    exc
                ),
            }

            stop_reason = (
                "Execution stopped safely because "
                "the next live move failed validation."
            )

            break

    # ---------------------------------------------------------
    # FINAL LIVE STATE
    # ---------------------------------------------------------

    final_entries = get_all_entries(
        db
    )

    final_snapshot = (
        build_timetable_snapshot(
            final_entries
        )
    )

    risk_cost_reduction = (
        baseline[
            "student_risk_cost"
        ]
        - final_snapshot[
            "student_risk_cost"
        ]
    )

    risk_count_reduction = (
        baseline[
            "student_risks"
        ][
            "total"
        ]
        - final_snapshot[
            "student_risks"
        ][
            "total"
        ]
    )

    group_reduction = (
        baseline[
            "student_groups"
        ]
        - final_snapshot[
            "student_groups"
        ]
    )

    clash_reduction = (
        baseline[
            "clashes"
        ][
            "total"
        ]
        - final_snapshot[
            "clashes"
        ][
            "total"
        ]
    )

    # ---------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------

    if (
        len(
            applied_steps
        )
        == max_steps
    ):
        status = "completed"

    elif applied_steps:
        status = "partial"

    else:
        status = "no_changes"

    return {
        "success": bool(
            applied_steps
        ),
        "status": status,
        "execution_id": (
            execution_id
        ),
        "requested_max_steps": (
            max_steps
        ),
        "applied_steps": len(
            applied_steps
        ),
        "stop_reason": (
            stop_reason
        ),
        "failed_step": (
            failed_step
        ),
        "baseline": (
            baseline
        ),
        "final_state": (
            final_snapshot
        ),
        "overall_improvement": {
            "student_risk_cost": {
                "before": (
                    baseline[
                        "student_risk_cost"
                    ]
                ),
                "after": (
                    final_snapshot[
                        "student_risk_cost"
                    ]
                ),
                "reduction": (
                    risk_cost_reduction
                ),
            },
            "student_risks": {
                "before": (
                    baseline[
                        "student_risks"
                    ][
                        "total"
                    ]
                ),
                "after": (
                    final_snapshot[
                        "student_risks"
                    ][
                        "total"
                    ]
                ),
                "reduction": (
                    risk_count_reduction
                ),
            },
            "student_groups": {
                "before": (
                    baseline[
                        "student_groups"
                    ]
                ),
                "after": (
                    final_snapshot[
                        "student_groups"
                    ]
                ),
                "reduction": (
                    group_reduction
                ),
            },
            "general_clashes": {
                "before": (
                    baseline[
                        "clashes"
                    ][
                        "total"
                    ]
                ),
                "after": (
                    final_snapshot[
                        "clashes"
                    ][
                        "total"
                    ]
                ),
                "reduction": (
                    clash_reduction
                ),
            },
        },
        "steps": (
            applied_steps
        ),
        "important_note": (
            "Each move was recalculated and validated against "
            "the live timetable immediately before it was applied. "
            "Earlier successful steps remain committed if a later "
            "step stops safely. Every applied move has an individual "
            "StudentScheduleChange history record and can use the "
            "existing undo/redo workflow."
        ),
    }