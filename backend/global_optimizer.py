from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backend.clash_detector import detect_clashes
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
)
from backend.student_conflict_groups import (
    build_student_conflict_groups,
)
from backend.student_conflict_resolver import (
    resolve_all_student_conflict_groups,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------


RISK_WEIGHT = {
    "confirmed": 100,
    "probable": 10,
    "possible": 2,
}


DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}


# ---------------------------------------------------------------------------
# BASIC METRICS
# ---------------------------------------------------------------------------


def calculate_student_risk_cost(
    risks: list[dict],
) -> int:
    return sum(
        RISK_WEIGHT.get(
            risk.get("risk_level"),
            0,
        )
        for risk in risks
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


def count_risk_levels(
    risks: list[dict],
) -> dict:
    return {
        "total": len(risks),
        "confirmed": sum(
            1
            for risk in risks
            if risk.get("risk_level")
            == "confirmed"
        ),
        "probable": sum(
            1
            for risk in risks
            if risk.get("risk_level")
            == "probable"
        ),
        "possible": sum(
            1
            for risk in risks
            if risk.get("risk_level")
            == "possible"
        ),
    }


# ---------------------------------------------------------------------------
# ENTRY CLONING
# ---------------------------------------------------------------------------


def clone_entry(
    entry,
):
    """
    Create a plain in-memory representation of a timetable entry.

    This prevents candidate simulations from mutating SQLAlchemy
    database objects.
    """

    return SimpleNamespace(
        id=entry.id,
        entry_kind=getattr(
            entry,
            "entry_kind",
            "course",
        ),
        course_code=getattr(
            entry,
            "course_code",
            None,
        ),
        course_name=getattr(
            entry,
            "course_name",
            None,
        ),
        semester=getattr(
            entry,
            "semester",
            None,
        ),
        section=getattr(
            entry,
            "section",
            None,
        ),
        faculty=getattr(
            entry,
            "faculty",
            None,
        ),
        room=getattr(
            entry,
            "room",
            None,
        ),
        day=getattr(
            entry,
            "day",
            None,
        ),
        start_time=getattr(
            entry,
            "start_time",
            None,
        ),
        end_time=getattr(
            entry,
            "end_time",
            None,
        ),
        class_type=getattr(
            entry,
            "class_type",
            None,
        ),
        raw_text=getattr(
            entry,
            "raw_text",
            None,
        ),
        source=getattr(
            entry,
            "source",
            None,
        ),
    )


def clone_entries(
    entries: list,
) -> list:
    return [
        clone_entry(entry)
        for entry in entries
    ]


# ---------------------------------------------------------------------------
# TIMETABLE SNAPSHOT
# ---------------------------------------------------------------------------


def build_timetable_snapshot(
    entries: list,
) -> dict:
    clashes = detect_clashes(
        entries
    )

    risks = analyze_student_conflicts(
        entries
    )

    groups = build_student_conflict_groups(
        risks
    )

    return {
        "entries": len(entries),
        "clashes": count_clash_types(
            clashes
        ),
        "student_risks": (
            count_risk_levels(
                risks
            )
        ),
        "student_risk_cost": (
            calculate_student_risk_cost(
                risks
            )
        ),
        "student_groups": len(
            groups
        ),
    }


# ---------------------------------------------------------------------------
# CANDIDATE SIMULATION
# ---------------------------------------------------------------------------


def simulate_candidate_move(
    entries: list,
    candidate: dict,
) -> list:
    """
    Simulate one candidate move without touching the database.
    """

    simulated = clone_entries(
        entries
    )

    target_id = candidate[
        "entry_id"
    ]

    move_to = candidate[
        "move_to"
    ]

    target = None

    for entry in simulated:
        if entry.id == target_id:
            target = entry
            break

    if target is None:
        raise ValueError(
            f"Timetable entry {target_id} "
            "was not found during simulation."
        )

    target.day = move_to[
        "day"
    ]

    target.start_time = (
        move_to[
            "start_time"
        ]
    )

    target.end_time = (
        move_to[
            "end_time"
        ]
    )

    return simulated


# ---------------------------------------------------------------------------
# CANDIDATE COLLECTION
# ---------------------------------------------------------------------------


def candidate_key(
    candidate: dict,
) -> tuple:
    move_to = candidate[
        "move_to"
    ]

    return (
        candidate["entry_id"],
        move_to["day"],
        move_to["start_time"],
        move_to["end_time"],
    )


def collect_candidate_moves(
    entries: list,
) -> list[dict]:
    """
    Collect currently feasible candidate moves generated by the
    existing student conflict resolver.

    Candidates requiring a new room are deliberately excluded from
    the first global optimizer version.
    """

    risks = analyze_student_conflicts(
        entries
    )

    groups = build_student_conflict_groups(
        risks
    )

    resolutions = (
        resolve_all_student_conflict_groups(
            groups,
            entries,
        )
    )

    unique: dict[
        tuple,
        dict,
    ] = {}

    for resolution in resolutions:
        group_id = resolution[
            "group_id"
        ]

        candidates: list[dict] = []

        best_fix = resolution.get(
            "best_fix"
        )

        if best_fix is not None:
            candidates.append(
                best_fix
            )

        candidates.extend(
            resolution.get(
                "alternatives",
                [],
            )
        )

        for candidate in candidates:
            if candidate.get(
                "room_status"
            ) not in {
                "available",
                "online",
            }:
                continue

            key = candidate_key(
                candidate
            )

            candidate_copy = dict(
                candidate
            )

            candidate_copy[
                "source_group_id"
            ] = group_id

            existing = unique.get(
                key
            )

            if existing is None:
                unique[
                    key
                ] = candidate_copy
                continue

            if (
                candidate_copy.get(
                    "score",
                    0,
                )
                > existing.get(
                    "score",
                    0,
                )
            ):
                unique[
                    key
                ] = candidate_copy

    return list(
        unique.values()
    )


# ---------------------------------------------------------------------------
# GLOBAL EVALUATION
# ---------------------------------------------------------------------------


def evaluate_candidate(
    entries: list,
    candidate: dict,
    baseline: dict,
) -> dict | None:
    simulated_entries = (
        simulate_candidate_move(
            entries,
            candidate,
        )
    )

    after = build_timetable_snapshot(
        simulated_entries
    )

    clashes_before = baseline[
        "clashes"
    ][
        "total"
    ]

    clashes_after = after[
        "clashes"
    ][
        "total"
    ]

    risk_cost_before = baseline[
        "student_risk_cost"
    ]

    risk_cost_after = after[
        "student_risk_cost"
    ]

    risks_before = baseline[
        "student_risks"
    ][
        "total"
    ]

    risks_after = after[
        "student_risks"
    ][
        "total"
    ]

    groups_before = baseline[
        "student_groups"
    ]

    groups_after = after[
        "student_groups"
    ]

    # ---------------------------------------------------------
    # HARD REJECTION RULES
    # ---------------------------------------------------------

    if clashes_after > clashes_before:
        return None

    if risk_cost_after >= risk_cost_before:
        return None

    if groups_after > groups_before:
        return None

    if (
        after[
            "student_risks"
        ][
            "confirmed"
        ]
        > baseline[
            "student_risks"
        ][
            "confirmed"
        ]
    ):
        return None

    # ---------------------------------------------------------
    # GLOBAL IMPROVEMENT
    # ---------------------------------------------------------

    risk_cost_reduction = (
        risk_cost_before
        - risk_cost_after
    )

    risk_count_reduction = (
        risks_before
        - risks_after
    )

    group_reduction = (
        groups_before
        - groups_after
    )

    clash_reduction = (
        clashes_before
        - clashes_after
    )

    # ---------------------------------------------------------
    # GLOBAL SCORE
    #
    # This is an explainable ranking score, not probability.
    # ---------------------------------------------------------

    global_score = 50

    global_score += min(
        risk_cost_reduction * 2,
        25,
    )

    global_score += min(
        max(
            risk_count_reduction,
            0,
        )
        * 5,
        15,
    )

    global_score += min(
        max(
            group_reduction,
            0,
        )
        * 5,
        10,
    )

    global_score += min(
        max(
            clash_reduction,
            0,
        )
        * 10,
        10,
    )

    local_score = candidate.get(
        "score",
        0,
    )

    global_score += min(
        int(
            local_score / 20
        ),
        5,
    )

    global_score = max(
        0,
        min(
            global_score,
            100,
        ),
    )

    reasons: list[str] = []

    if risk_cost_reduction > 0:
        reasons.append(
            f"Reduces global student/cohort risk cost "
            f"by {risk_cost_reduction}."
        )

    if risk_count_reduction > 0:
        reasons.append(
            f"Removes {risk_count_reduction} "
            f"student/cohort risk record(s)."
        )

    if group_reduction > 0:
        reasons.append(
            f"Reduces conflict groups by "
            f"{group_reduction}."
        )

    if clash_reduction > 0:
        reasons.append(
            f"Removes {clash_reduction} "
            f"general timetable clash(es)."
        )

    if clashes_after == 0:
        reasons.append(
            "Leaves the timetable free of "
            "general room/faculty clashes."
        )

    if candidate.get(
        "room_status"
    ) == "available":
        reasons.append(
            "Existing room remains available "
            "at the destination slot."
        )

    if candidate.get(
        "room_status"
    ) == "online":
        reasons.append(
            "Online class requires no physical room."
        )

    return {
        "source_group_id": (
            candidate[
                "source_group_id"
            ]
        ),
        "entry_id": (
            candidate[
                "entry_id"
            ]
        ),
        "course_code": (
            candidate.get(
                "course_code"
            )
        ),
        "course_name": (
            candidate.get(
                "course_name"
            )
        ),
        "section": (
            candidate.get(
                "section"
            )
        ),
        "faculty": (
            candidate.get(
                "faculty"
            )
        ),
        "room": (
            candidate.get(
                "current_room"
            )
        ),
        "class_type": (
            candidate.get(
                "class_type"
            )
        ),
        "move_from": (
            candidate[
                "move_from"
            ]
        ),
        "move_to": (
            candidate[
                "move_to"
            ]
        ),
        "local_score": (
            candidate.get(
                "score",
                0,
            )
        ),
        "global_score": (
            global_score
        ),
        "room_status": (
            candidate.get(
                "room_status"
            )
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
                    risk_cost_reduction
                ),
            },
            "student_risks": {
                "before": risks_before,
                "after": risks_after,
                "reduction": (
                    risk_count_reduction
                ),
            },
            "student_groups": {
                "before": groups_before,
                "after": groups_after,
                "reduction": (
                    group_reduction
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
                    clash_reduction
                ),
            },
        },
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# GLOBAL OPTIMIZER
# ---------------------------------------------------------------------------


def optimize_timetable_globally(
    entries: list,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Evaluate feasible timetable moves against the complete timetable.

    This function is READ-ONLY.

    It does not:
    - modify SQLAlchemy objects
    - write to the database
    - commit changes
    - automatically apply suggestions
    """

    baseline = build_timetable_snapshot(
        entries
    )

    candidates = collect_candidate_moves(
        entries
    )

    evaluated: list[
        dict
    ] = []

    rejected = 0

    for candidate in candidates:
        result = evaluate_candidate(
            entries,
            candidate,
            baseline,
        )

        if result is None:
            rejected += 1
            continue

        evaluated.append(
            result
        )

    evaluated.sort(
        key=lambda item: (
            -item["global_score"],
            -item[
                "improvement"
            ][
                "student_risk_cost"
            ][
                "reduction"
            ],
            -item[
                "improvement"
            ][
                "student_risks"
            ][
                "reduction"
            ],
            -item[
                "improvement"
            ][
                "student_groups"
            ][
                "reduction"
            ],
            -item[
                "local_score"
            ],
            DAY_ORDER.get(
                item[
                    "move_to"
                ][
                    "day"
                ],
                99,
            ),
            item[
                "move_to"
            ][
                "start_time"
            ],
            item[
                "entry_id"
            ],
        )
    )

    best_move = (
        evaluated[0]
        if evaluated
        else None
    )

    return {
        "baseline": baseline,
        "candidate_summary": {
            "generated": len(
                candidates
            ),
            "globally_safe": len(
                evaluated
            ),
            "rejected": rejected,
        },
        "best_move": best_move,
        "ranked_moves": (
            evaluated[:limit]
        ),
        "important_note": (
            "Global scores rank timetable-wide improvement. "
            "They are deterministic planning scores, not "
            "probabilities or confirmed student enrollment data."
        ),
    }