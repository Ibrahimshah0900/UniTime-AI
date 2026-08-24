from __future__ import annotations

from typing import Any

from backend.global_optimizer import (
    build_timetable_snapshot,
    clone_entries,
    optimize_timetable_globally,
    simulate_candidate_move,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_MAX_STEPS = 10
MAX_ALLOWED_STEPS = 50


# ---------------------------------------------------------------------------
# MOVE SELECTION
# ---------------------------------------------------------------------------


def select_next_move(
    optimization_result: dict,
    *,
    already_moved_entry_ids: set[int],
) -> dict | None:
    """
    Select the next globally ranked move.

    During one optimization plan we avoid moving the same timetable
    entry twice. This prevents simple oscillations such as:

        A -> B -> A

    and keeps the first planner version easy to audit.
    """

    ranked_moves = optimization_result.get(
        "ranked_moves",
        [],
    )

    for move in ranked_moves:
        entry_id = move.get(
            "entry_id"
        )

        if entry_id is None:
            continue

        if entry_id in already_moved_entry_ids:
            continue

        return move

    return None


# ---------------------------------------------------------------------------
# STEP RECORD
# ---------------------------------------------------------------------------


def build_step_record(
    *,
    step_number: int,
    move: dict,
    before: dict,
    after: dict,
) -> dict:
    risk_cost_before = before[
        "student_risk_cost"
    ]

    risk_cost_after = after[
        "student_risk_cost"
    ]

    risk_count_before = before[
        "student_risks"
    ][
        "total"
    ]

    risk_count_after = after[
        "student_risks"
    ][
        "total"
    ]

    groups_before = before[
        "student_groups"
    ]

    groups_after = after[
        "student_groups"
    ]

    clashes_before = before[
        "clashes"
    ][
        "total"
    ]

    clashes_after = after[
        "clashes"
    ][
        "total"
    ]

    return {
        "step": step_number,
        "entry_id": move[
            "entry_id"
        ],
        "course_code": move.get(
            "course_code"
        ),
        "course_name": move.get(
            "course_name"
        ),
        "section": move.get(
            "section"
        ),
        "faculty": move.get(
            "faculty"
        ),
        "room": move.get(
            "room"
        ),
        "class_type": move.get(
            "class_type"
        ),
        "source_group_id": move.get(
            "source_group_id"
        ),
        "move_from": move[
            "move_from"
        ],
        "move_to": move[
            "move_to"
        ],
        "local_score": move.get(
            "local_score"
        ),
        "global_score": move.get(
            "global_score"
        ),
        "room_status": move.get(
            "room_status"
        ),
        "improvement": {
            "student_risk_cost": {
                "before": (
                    risk_cost_before
                ),
                "after": (
                    risk_cost_after
                ),
                "reduction": (
                    risk_cost_before
                    - risk_cost_after
                ),
            },
            "student_risks": {
                "before": (
                    risk_count_before
                ),
                "after": (
                    risk_count_after
                ),
                "reduction": (
                    risk_count_before
                    - risk_count_after
                ),
            },
            "student_groups": {
                "before": (
                    groups_before
                ),
                "after": (
                    groups_after
                ),
                "reduction": (
                    groups_before
                    - groups_after
                ),
            },
            "general_clashes": {
                "before": (
                    clashes_before
                ),
                "after": (
                    clashes_after
                ),
                "reduction": (
                    clashes_before
                    - clashes_after
                ),
            },
        },
        "reasons": move.get(
            "reasons",
            [],
        ),
    }


# ---------------------------------------------------------------------------
# SAFETY CHECK
# ---------------------------------------------------------------------------


def validate_simulated_step(
    *,
    before: dict,
    after: dict,
) -> bool:
    """
    Extra planner-level safety validation.

    The underlying global optimizer already rejects unsafe moves,
    but this check verifies the simulated result again before it is
    accepted into a multi-step plan.
    """

    if (
        after["clashes"]["total"]
        > before["clashes"]["total"]
    ):
        return False

    if (
        after["student_risk_cost"]
        >= before["student_risk_cost"]
    ):
        return False

    if (
        after["student_groups"]
        > before["student_groups"]
    ):
        return False

    if (
        after[
            "student_risks"
        ][
            "confirmed"
        ]
        > before[
            "student_risks"
        ][
            "confirmed"
        ]
    ):
        return False

    return True


# ---------------------------------------------------------------------------
# MULTI-STEP PLANNER
# ---------------------------------------------------------------------------


def build_multi_step_optimization_plan(
    entries: list,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[str, Any]:
    """
    Build a read-only sequence of globally beneficial timetable moves.

    Nothing is written to the database.

    Algorithm:

    1. Clone the live timetable.
    2. Measure the baseline.
    3. Run the global optimizer.
    4. Select the highest-ranked move for an entry not already moved.
    5. Simulate that move in memory.
    6. Recalculate the complete timetable.
    7. Accept the step only if:
         - global student risk decreases,
         - confirmed risk does not increase,
         - general clashes do not increase.
    8. Repeat from the improved simulated timetable.
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

    simulated_entries = clone_entries(
        entries
    )

    baseline = build_timetable_snapshot(
        simulated_entries
    )

    current_snapshot = baseline

    already_moved_entry_ids: set[int] = set()

    steps: list[dict] = []

    stop_reason = (
        "Maximum requested steps reached."
    )

    rejected_during_planning = 0

    for step_number in range(
        1,
        max_steps + 1,
    ):
        optimization = (
            optimize_timetable_globally(
                simulated_entries,
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

        next_move = select_next_move(
            optimization,
            already_moved_entry_ids=(
                already_moved_entry_ids
            ),
        )

        if next_move is None:
            stop_reason = (
                "All remaining candidate moves "
                "belong to timetable entries already "
                "moved by this plan."
            )
            break

        candidate_entries = (
            simulate_candidate_move(
                simulated_entries,
                next_move,
            )
        )

        candidate_snapshot = (
            build_timetable_snapshot(
                candidate_entries
            )
        )

        if not validate_simulated_step(
            before=current_snapshot,
            after=candidate_snapshot,
        ):
            rejected_during_planning += 1

            already_moved_entry_ids.add(
                next_move[
                    "entry_id"
                ]
            )

            continue

        step_record = (
            build_step_record(
                step_number=(
                    len(steps) + 1
                ),
                move=next_move,
                before=current_snapshot,
                after=candidate_snapshot,
            )
        )

        steps.append(
            step_record
        )

        already_moved_entry_ids.add(
            next_move[
                "entry_id"
            ]
        )

        simulated_entries = (
            candidate_entries
        )

        current_snapshot = (
            candidate_snapshot
        )

    projected_final = (
        current_snapshot
    )

    total_risk_cost_reduction = (
        baseline[
            "student_risk_cost"
        ]
        - projected_final[
            "student_risk_cost"
        ]
    )

    total_risk_count_reduction = (
        baseline[
            "student_risks"
        ][
            "total"
        ]
        - projected_final[
            "student_risks"
        ][
            "total"
        ]
    )

    total_group_reduction = (
        baseline[
            "student_groups"
        ]
        - projected_final[
            "student_groups"
        ]
    )

    total_clash_reduction = (
        baseline[
            "clashes"
        ][
            "total"
        ]
        - projected_final[
            "clashes"
        ][
            "total"
        ]
    )

    return {
        "requested_max_steps": (
            max_steps
        ),
        "planned_steps": len(
            steps
        ),
        "stop_reason": (
            stop_reason
        ),
        "baseline": baseline,
        "projected_final": (
            projected_final
        ),
        "overall_improvement": {
            "student_risk_cost": {
                "before": baseline[
                    "student_risk_cost"
                ],
                "after": (
                    projected_final[
                        "student_risk_cost"
                    ]
                ),
                "reduction": (
                    total_risk_cost_reduction
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
                    projected_final[
                        "student_risks"
                    ][
                        "total"
                    ]
                ),
                "reduction": (
                    total_risk_count_reduction
                ),
            },
            "student_groups": {
                "before": (
                    baseline[
                        "student_groups"
                    ]
                ),
                "after": (
                    projected_final[
                        "student_groups"
                    ]
                ),
                "reduction": (
                    total_group_reduction
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
                    projected_final[
                        "clashes"
                    ][
                        "total"
                    ]
                ),
                "reduction": (
                    total_clash_reduction
                ),
            },
        },
        "planner_statistics": {
            "unique_entries_moved": len(
                already_moved_entry_ids
            ),
            "rejected_during_planning": (
                rejected_during_planning
            ),
        },
        "steps": steps,
        "important_note": (
            "This is a read-only projected optimization plan. "
            "No timetable records have been changed. Each step "
            "is recalculated against the simulated result of all "
            "previous steps. Student/cohort risks remain inferred "
            "without individual enrollment data."
        ),
    }