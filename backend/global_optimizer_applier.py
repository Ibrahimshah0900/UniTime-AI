from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.global_optimizer import (
    calculate_student_risk_cost,
    optimize_timetable_globally,
)
from backend.models import TimetableEntry
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
)
from backend.student_resolution_applier import (
    StudentScheduleChange,
    get_all_entries,
    validate_specific_destination,
)


# ---------------------------------------------------------------------------
# LIVE GLOBAL BEST MOVE
# ---------------------------------------------------------------------------


def get_live_global_best_move(
    entries: list[TimetableEntry],
) -> dict:
    """
    Recalculate the optimizer from the current live timetable.

    No previously returned API suggestion is trusted.
    """

    result = optimize_timetable_globally(
        entries,
        limit=1,
    )

    best_move = result.get(
        "best_move"
    )

    if best_move is None:
        raise ValueError(
            "No globally beneficial timetable move "
            "is currently available."
        )

    if best_move.get(
        "room_status"
    ) not in {
        "available",
        "online",
    }:
        raise ValueError(
            "The current global best move is not "
            "fully feasible because its room "
            "requirements are unresolved."
        )

    return best_move


# ---------------------------------------------------------------------------
# CURRENT ENTRY STATE VALIDATION
# ---------------------------------------------------------------------------


def validate_global_entry_state(
    entry: TimetableEntry,
    best_move: dict,
) -> None:
    move_from = best_move[
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
            "The timetable entry changed after the "
            "global optimization result was calculated. "
            "Recalculate the optimizer before applying."
        )


# ---------------------------------------------------------------------------
# SAFETY HELPERS
# ---------------------------------------------------------------------------


def count_confirmed_risks(
    risks: list[dict],
) -> int:
    return sum(
        1
        for risk in risks
        if risk.get(
            "risk_level"
        )
        == "confirmed"
    )


def count_clash_types(
    clashes: list[dict],
) -> dict:
    room = sum(
        1
        for clash in clashes
        if clash.get("type")
        == "room"
    )

    faculty = sum(
        1
        for clash in clashes
        if clash.get("type")
        == "faculty"
    )

    other = (
        len(clashes)
        - room
        - faculty
    )

    return {
        "total": len(
            clashes
        ),
        "room": room,
        "faculty": faculty,
        "other": other,
    }


def validate_global_improvement(
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

    if (
        risk_cost_after
        >= risk_cost_before
    ):
        raise ValueError(
            "Global move rejected because it does "
            "not reduce total student/cohort risk."
        )

    if (
        confirmed_after
        > confirmed_before
    ):
        raise ValueError(
            "Global move rejected because it creates "
            "additional confirmed student conflicts."
        )

    if (
        len(clashes_after)
        > len(clashes_before)
    ):
        raise ValueError(
            "Global move rejected because it creates "
            "additional room, faculty, or other "
            "general timetable clashes."
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
    }


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------


def create_global_change_record(
    db: Session,
    *,
    entry: TimetableEntry,
    best_move: dict,
    old_day: str,
    old_start_time: str,
    old_end_time: str,
    risk_validation: dict,
) -> StudentScheduleChange:
    """
    Reuse the existing student_schedule_changes table.

    This means global optimizer moves automatically remain
    compatible with the existing student schedule undo/redo
    mechanism.
    """

    move_to = best_move[
        "move_to"
    ]

    change = StudentScheduleChange(
        entry_id=entry.id,
        group_id=best_move[
            "source_group_id"
        ],
        change_type=(
            "global_optimizer_move"
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
            best_move[
                "global_score"
            ]
        ),
        reasons_json=json.dumps(
            best_move.get(
                "reasons",
                [],
            )
        ),
        risk_cost_before=(
            risk_validation[
                "risk_cost_before"
            ]
        ),
        risk_cost_after=(
            risk_validation[
                "risk_cost_after"
            ]
        ),
        total_risks_before=(
            risk_validation[
                "student_risks_before"
            ]
        ),
        total_risks_after=(
            risk_validation[
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
# SAFE GLOBAL APPLY
# ---------------------------------------------------------------------------


def apply_global_best_move(
    db: Session,
) -> dict[str, Any]:
    """
    Safely apply the CURRENT globally best timetable move.

    Safety process:

    1. Load the current live timetable.
    2. Recalculate the global optimizer.
    3. Ignore any stale suggestion from the frontend.
    4. Verify the selected timetable entry still matches.
    5. Re-check faculty availability.
    6. Re-check room availability.
    7. Record risks and general clashes before the move.
    8. Apply the move provisionally inside the transaction.
    9. Recalculate all risks and clashes.
    10. Reject and rollback if global conditions worsen.
    11. Record history.
    12. Commit only after all validations pass.
    """

    try:
        # -----------------------------------------------------
        # LIVE TIMETABLE
        # -----------------------------------------------------

        entries_before = (
            get_all_entries(
                db
            )
        )

        # -----------------------------------------------------
        # LIVE GLOBAL OPTIMIZATION
        # -----------------------------------------------------

        best_move = (
            get_live_global_best_move(
                entries_before
            )
        )

        entry = db.get(
            TimetableEntry,
            best_move[
                "entry_id"
            ],
        )

        if entry is None:
            raise ValueError(
                "The timetable entry selected by "
                "the global optimizer no longer exists."
            )

        # -----------------------------------------------------
        # STALE STATE PROTECTION
        # -----------------------------------------------------

        validate_global_entry_state(
            entry,
            best_move,
        )

        move_from = best_move[
            "move_from"
        ]

        move_to = best_move[
            "move_to"
        ]

        # -----------------------------------------------------
        # LIVE FACULTY / ROOM VALIDATION
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # BASELINE
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # PROVISIONAL MOVE
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # RELOAD TRANSACTION STATE
        # -----------------------------------------------------

        entries_after = (
            get_all_entries(
                db
            )
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

        # -----------------------------------------------------
        # GLOBAL SAFETY VALIDATION
        # -----------------------------------------------------

        risk_validation = (
            validate_global_improvement(
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

        # -----------------------------------------------------
        # VERIFY OPTIMIZER PREDICTION
        # -----------------------------------------------------

        predicted = best_move[
            "improvement"
        ]

        actual_risk_reduction = (
            risk_validation[
                "risk_cost_reduction"
            ]
        )

        predicted_risk_reduction = (
            predicted[
                "student_risk_cost"
            ][
                "reduction"
            ]
        )

        prediction_matches = (
            actual_risk_reduction
            == predicted_risk_reduction
        )

        # We do not reject solely because a prediction differs.
        # Live safety validation above is authoritative.
        # This field helps detect future optimizer inconsistencies.

        # -----------------------------------------------------
        # HISTORY
        # -----------------------------------------------------

        history = (
            create_global_change_record(
                db,
                entry=entry,
                best_move=best_move,
                old_day=old_day,
                old_start_time=(
                    old_start_time
                ),
                old_end_time=(
                    old_end_time
                ),
                risk_validation=(
                    risk_validation
                ),
            )
        )

        db.flush()

        # -----------------------------------------------------
        # COMMIT
        # -----------------------------------------------------

        db.commit()

        db.refresh(
            entry
        )

        db.refresh(
            history
        )

        return {
            "success": True,
            "message": (
                "Global optimizer best move "
                "applied successfully."
            ),
            "change_id": (
                history.id
            ),
            "change_type": (
                history.change_type
            ),
            "source_group_id": (
                best_move[
                    "source_group_id"
                ]
            ),
            "applied_move": {
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
                "move_from": {
                    "day": (
                        move_from[
                            "day"
                        ]
                    ),
                    "start_time": (
                        move_from[
                            "start_time"
                        ]
                    ),
                    "end_time": (
                        move_from[
                            "end_time"
                        ]
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
                    best_move[
                        "local_score"
                    ]
                ),
                "global_score": (
                    best_move[
                        "global_score"
                    ]
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
                "reasons": (
                    best_move.get(
                        "reasons",
                        [],
                    )
                ),
            },
            "global_validation": {
                "student_risk_cost": {
                    "before": (
                        risk_validation[
                            "risk_cost_before"
                        ]
                    ),
                    "after": (
                        risk_validation[
                            "risk_cost_after"
                        ]
                    ),
                    "reduction": (
                        risk_validation[
                            "risk_cost_reduction"
                        ]
                    ),
                },
                "student_risks": {
                    "before": (
                        risk_validation[
                            "student_risks_before"
                        ]
                    ),
                    "after": (
                        risk_validation[
                            "student_risks_after"
                        ]
                    ),
                    "reduction": (
                        risk_validation[
                            "student_risks_reduction"
                        ]
                    ),
                },
                "confirmed_risks": {
                    "before": (
                        risk_validation[
                            "confirmed_before"
                        ]
                    ),
                    "after": (
                        risk_validation[
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
                    predicted_risk_reduction
                ),
                "actual_risk_cost_reduction": (
                    actual_risk_reduction
                ),
                "prediction_matches": (
                    prediction_matches
                ),
            },
            "warning": (
                "The global optimizer is based on "
                "timetable-derived student/cohort risk. "
                "It does not represent confirmed "
                "individual student enrollment data."
            ),
        }

    except Exception:
        db.rollback()
        raise