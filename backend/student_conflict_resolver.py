from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable

from backend.student_conflict_analyzer import (
    classify_student_conflict,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}

RISK_WEIGHT = {
    "confirmed": 100,
    "probable": 10,
    "possible": 2,
}


# ---------------------------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------------------------


def normalize(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    value = value.strip().lower()

    return value or None


def time_to_minutes(
    value: str,
) -> int:
    hour, minute = map(
        int,
        value.split(":"),
    )

    return (
        hour * 60
        + minute
    )


def duration_minutes(
    start_time: str,
    end_time: str,
) -> int:
    return (
        time_to_minutes(end_time)
        - time_to_minutes(start_time)
    )


def times_overlap(
    first_start: str,
    first_end: str,
    second_start: str,
    second_end: str,
) -> bool:
    return (
        first_start < second_end
        and second_start < first_end
    )


# ---------------------------------------------------------------------------
# CANDIDATE SLOT DISCOVERY
# ---------------------------------------------------------------------------


def build_candidate_slots(
    entries: Iterable,
) -> list[dict]:
    """
    Build candidate slots from real timetable slots.

    No arbitrary times are invented.
    """

    slots: set[
        tuple[str, str, str]
    ] = set()

    for entry in entries:
        if (
            getattr(
                entry,
                "entry_kind",
                "course",
            )
            != "course"
        ):
            continue

        if (
            not entry.day
            or not entry.start_time
            or not entry.end_time
        ):
            continue

        slots.add(
            (
                entry.day,
                entry.start_time,
                entry.end_time,
            )
        )

    ordered = sorted(
        slots,
        key=lambda item: (
            DAY_ORDER.get(
                item[0],
                99,
            ),
            item[1],
            item[2],
        ),
    )

    return [
        {
            "day": day,
            "start_time": start_time,
            "end_time": end_time,
        }
        for (
            day,
            start_time,
            end_time,
        ) in ordered
    ]


# ---------------------------------------------------------------------------
# FACULTY CONSTRAINT
# ---------------------------------------------------------------------------


def faculty_is_available(
    target,
    *,
    day: str,
    start_time: str,
    end_time: str,
    entries: Iterable,
) -> bool:
    faculty = normalize(
        target.faculty
    )

    if faculty in {
        None,
        "tba",
    }:
        return True

    for entry in entries:
        if entry.id == target.id:
            continue

        if normalize(
            entry.day
        ) != normalize(day):
            continue

        if normalize(
            entry.faculty
        ) != faculty:
            continue

        if times_overlap(
            start_time,
            end_time,
            entry.start_time,
            entry.end_time,
        ):
            return False

    return True


# ---------------------------------------------------------------------------
# ROOM CONSTRAINT
# ---------------------------------------------------------------------------


def get_room_status_for_candidate(
    target,
    *,
    day: str,
    start_time: str,
    end_time: str,
    entries: Iterable,
) -> dict:
    """
    Returns explicit room feasibility information.

    Physical room assigned:
        room_status = available / occupied
        room_available = True / False

    No room assigned:
        room_status = requires_assignment
        room_available = None

    Online:
        room_status = online
        room_available = True
    """

    room = normalize(
        target.room
    )

    if room is None:
        return {
            "room_status": (
                "requires_assignment"
            ),
            "room_available": None,
            "current_room": None,
        }

    if room == "online":
        return {
            "room_status": "online",
            "room_available": True,
            "current_room": target.room,
        }

    for entry in entries:
        if entry.id == target.id:
            continue

        if normalize(
            entry.day
        ) != normalize(day):
            continue

        if normalize(
            entry.room
        ) != room:
            continue

        if times_overlap(
            start_time,
            end_time,
            entry.start_time,
            entry.end_time,
        ):
            return {
                "room_status": "occupied",
                "room_available": False,
                "current_room": target.room,
            }

    return {
        "room_status": "available",
        "room_available": True,
        "current_room": target.room,
    }


# ---------------------------------------------------------------------------
# SIMULATION
# ---------------------------------------------------------------------------


def simulate_entry_at_slot(
    target,
    *,
    day: str,
    start_time: str,
    end_time: str,
):
    """
    Create an in-memory copy for conflict analysis.

    The actual SQLAlchemy object is never modified.
    """

    return SimpleNamespace(
        id=target.id,
        entry_kind=getattr(
            target,
            "entry_kind",
            "course",
        ),
        course_code=target.course_code,
        course_name=target.course_name,
        semester=target.semester,
        section=target.section,
        faculty=target.faculty,
        room=target.room,
        day=day,
        start_time=start_time,
        end_time=end_time,
        class_type=target.class_type,
        raw_text=target.raw_text,
        source=getattr(
            target,
            "source",
            None,
        ),
    )


# ---------------------------------------------------------------------------
# STUDENT / COHORT RISKS
# ---------------------------------------------------------------------------


def student_risks_for_entry(
    target,
    entries: Iterable,
) -> list[dict]:
    risks: list[dict] = []

    for other in entries:
        if other.id == target.id:
            continue

        if (
            getattr(
                other,
                "entry_kind",
                "course",
            )
            != "course"
        ):
            continue

        result = (
            classify_student_conflict(
                target,
                other,
            )
        )

        if result is not None:
            risks.append(
                result
            )

    return risks


def student_risks_for_candidate(
    target,
    *,
    day: str,
    start_time: str,
    end_time: str,
    entries: Iterable,
) -> list[dict]:
    simulated = (
        simulate_entry_at_slot(
            target,
            day=day,
            start_time=start_time,
            end_time=end_time,
        )
    )

    return student_risks_for_entry(
        simulated,
        entries,
    )


def risk_counts(
    risks: list[dict],
) -> dict:
    return {
        "total": len(
            risks
        ),
        "confirmed": sum(
            1
            for risk in risks
            if risk["risk_level"]
            == "confirmed"
        ),
        "probable": sum(
            1
            for risk in risks
            if risk["risk_level"]
            == "probable"
        ),
        "possible": sum(
            1
            for risk in risks
            if risk["risk_level"]
            == "possible"
        ),
    }


def risk_cost(
    risks: list[dict],
) -> int:
    return sum(
        RISK_WEIGHT.get(
            risk["risk_level"],
            0,
        )
        for risk in risks
    )


# ---------------------------------------------------------------------------
# MOVE SCORING
# ---------------------------------------------------------------------------


def score_candidate_move(
    target,
    *,
    candidate_day: str,
    candidate_start: str,
    risks_before: list[dict],
    risks_after: list[dict],
    room_status: str,
) -> tuple[int, list[str]]:
    """
    Explainable heuristic ranking score.

    This is not AI confidence or probability.
    """

    score = 75

    reasons: list[str] = []

    before_cost = risk_cost(
        risks_before
    )

    after_cost = risk_cost(
        risks_after
    )

    improvement = (
        before_cost
        - after_cost
    )

    # ---------------------------------------------------------
    # CONFLICT IMPROVEMENT
    # ---------------------------------------------------------

    if after_cost == 0:
        score += 18

        reasons.append(
            "Removes all detected student/cohort risks "
            "for this timetable entry."
        )

    elif improvement > 0:
        score += min(
            improvement,
            15,
        )

        reasons.append(
            "Reduces detected student/cohort conflict risk."
        )

    # ---------------------------------------------------------
    # SAME DAY / DAY CHANGE
    # ---------------------------------------------------------

    if (
        candidate_day
        == target.day
    ):
        score += 4

        reasons.append(
            "Keeps the class on the same day."
        )

    else:
        day_distance = abs(
            DAY_ORDER.get(
                candidate_day,
                99,
            )
            - DAY_ORDER.get(
                target.day,
                99,
            )
        )

        score -= min(
            3 * day_distance,
            12,
        )

        reasons.append(
            "Moves the class to a different day."
        )

    # ---------------------------------------------------------
    # TIME SHIFT
    # ---------------------------------------------------------

    old_start = time_to_minutes(
        target.start_time
    )

    new_start = time_to_minutes(
        candidate_start
    )

    shift = abs(
        new_start
        - old_start
    )

    if shift <= 90:
        score += 3

        reasons.append(
            "Requires only a small time shift."
        )

    elif shift <= 180:
        score -= 3

        reasons.append(
            "Requires a moderate time shift."
        )

    else:
        score -= 8

        reasons.append(
            "Requires a large time shift."
        )

    # ---------------------------------------------------------
    # ROOM STATUS
    # ---------------------------------------------------------

    if room_status == "available":
        score += 2

        reasons.append(
            "Current room is available at the proposed slot."
        )

    elif room_status == "online":
        score += 2

        reasons.append(
            "Class is online, so no physical room is required."
        )

    elif room_status == "requires_assignment":
        score -= 6

        reasons.append(
            "A room still needs to be assigned for the proposed slot."
        )

    # ---------------------------------------------------------
    # REMAINING RISKS
    # ---------------------------------------------------------

    after_counts = risk_counts(
        risks_after
    )

    if (
        after_counts[
            "probable"
        ]
        > 0
    ):
        score -= (
            after_counts[
                "probable"
            ]
            * 8
        )

        reasons.append(
            "Some probable cohort risks would remain."
        )

    if (
        after_counts[
            "possible"
        ]
        > 0
    ):
        score -= (
            after_counts[
                "possible"
            ]
            * 2
        )

        reasons.append(
            "Some lower-confidence student risks would remain."
        )

    score = max(
        0,
        min(
            score,
            100,
        ),
    )

    return (
        score,
        reasons,
    )


# ---------------------------------------------------------------------------
# ENTRY MOVE SEARCH
# ---------------------------------------------------------------------------


def suggest_moves_for_entry(
    target,
    entries: list,
    *,
    limit: int = 5,
) -> list[dict]:
    """
    Search safer timetable slots for one entry.

    Requirements:
    - preserve class duration
    - faculty must be available
    - assigned room must be available
    - if no room exists, explicitly mark room assignment required
    - do not create confirmed student conflict
    - student/cohort risk must improve
    """

    target_duration = (
        duration_minutes(
            target.start_time,
            target.end_time,
        )
    )

    risks_before = (
        student_risks_for_entry(
            target,
            entries,
        )
    )

    before_cost = risk_cost(
        risks_before
    )

    suggestions: list[dict] = []

    slots = build_candidate_slots(
        entries
    )

    for slot in slots:
        # -----------------------------------------------------
        # SKIP CURRENT SLOT
        # -----------------------------------------------------

        if (
            slot["day"]
            == target.day
            and slot[
                "start_time"
            ]
            == target.start_time
            and slot[
                "end_time"
            ]
            == target.end_time
        ):
            continue

        # -----------------------------------------------------
        # PRESERVE DURATION
        # -----------------------------------------------------

        candidate_duration = (
            duration_minutes(
                slot[
                    "start_time"
                ],
                slot[
                    "end_time"
                ],
            )
        )

        if (
            candidate_duration
            != target_duration
        ):
            continue

        # -----------------------------------------------------
        # FACULTY CHECK
        # -----------------------------------------------------

        faculty_available = (
            faculty_is_available(
                target,
                day=slot["day"],
                start_time=slot[
                    "start_time"
                ],
                end_time=slot[
                    "end_time"
                ],
                entries=entries,
            )
        )

        if not faculty_available:
            continue

        # -----------------------------------------------------
        # ROOM CHECK
        # -----------------------------------------------------

        room_info = (
            get_room_status_for_candidate(
                target,
                day=slot["day"],
                start_time=slot[
                    "start_time"
                ],
                end_time=slot[
                    "end_time"
                ],
                entries=entries,
            )
        )

        # Assigned physical room exists but is occupied.
        if (
            room_info[
                "room_status"
            ]
            == "occupied"
        ):
            continue

        # -----------------------------------------------------
        # STUDENT RISK CHECK
        # -----------------------------------------------------

        risks_after = (
            student_risks_for_candidate(
                target,
                day=slot["day"],
                start_time=slot[
                    "start_time"
                ],
                end_time=slot[
                    "end_time"
                ],
                entries=entries,
            )
        )

        after_counts = risk_counts(
            risks_after
        )

        if (
            after_counts[
                "confirmed"
            ]
            > 0
        ):
            continue

        after_cost = risk_cost(
            risks_after
        )

        if (
            after_cost
            >= before_cost
        ):
            continue

        # -----------------------------------------------------
        # SCORE
        # -----------------------------------------------------

        score, reasons = (
            score_candidate_move(
                target,
                candidate_day=slot[
                    "day"
                ],
                candidate_start=slot[
                    "start_time"
                ],
                risks_before=risks_before,
                risks_after=risks_after,
                room_status=room_info[
                    "room_status"
                ],
            )
        )

        suggestions.append(
            {
                "entry_id": (
                    target.id
                ),
                "course_code": (
                    target.course_code
                ),
                "course_name": (
                    target.course_name
                ),
                "section": (
                    target.section
                ),
                "faculty": (
                    target.faculty
                ),
                "current_room": (
                    target.room
                ),
                "class_type": (
                    target.class_type
                ),
                "move_from": {
                    "day": (
                        target.day
                    ),
                    "start_time": (
                        target.start_time
                    ),
                    "end_time": (
                        target.end_time
                    ),
                },
                "move_to": {
                    "day": (
                        slot["day"]
                    ),
                    "start_time": (
                        slot[
                            "start_time"
                        ]
                    ),
                    "end_time": (
                        slot[
                            "end_time"
                        ]
                    ),
                },
                "score": score,
                "faculty_available": (
                    faculty_available
                ),
                "room_status": (
                    room_info[
                        "room_status"
                    ]
                ),
                "room_available": (
                    room_info[
                        "room_available"
                    ]
                ),
                "risk_before": (
                    risk_counts(
                        risks_before
                    )
                ),
                "risk_after": (
                    after_counts
                ),
                "risk_cost_before": (
                    before_cost
                ),
                "risk_cost_after": (
                    after_cost
                ),
                "reasons": reasons,
            }
        )

    suggestions.sort(
        key=lambda item: (
            -item["score"],
            item[
                "room_status"
            ]
            == "requires_assignment",
            item[
                "risk_cost_after"
            ],
            item[
                "risk_after"
            ][
                "probable"
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
        )
    )

    return suggestions[
        :limit
    ]


# ---------------------------------------------------------------------------
# GROUP RESOLUTION
# ---------------------------------------------------------------------------


def resolve_student_conflict_group(
    group: dict,
    entries: list,
    *,
    limit_per_entry: int = 3,
) -> dict:
    """
    Generate ranked suggestions for one student conflict group.

    Nothing is written to the database.
    """

    entry_lookup = {
        entry.id: entry
        for entry in entries
    }

    all_moves: list[
        dict
    ] = []

    for group_entry in group.get(
        "entries",
        [],
    ):
        target = entry_lookup.get(
            group_entry["id"]
        )

        if target is None:
            continue

        suggestions = (
            suggest_moves_for_entry(
                target,
                entries,
                limit=limit_per_entry,
            )
        )

        all_moves.extend(
            suggestions
        )

    all_moves.sort(
        key=lambda item: (
            -item["score"],
            item[
                "room_status"
            ]
            == "requires_assignment",
            item[
                "risk_cost_after"
            ],
            item[
                "risk_after"
            ][
                "probable"
            ],
            item["entry_id"],
        )
    )

    best_fix = (
        all_moves[0]
        if all_moves
        else None
    )

    return {
        "group_id": (
            group["group_id"]
        ),
        "risk_level": (
            group["risk_level"]
        ),
        "priority_score": (
            group[
                "priority_score"
            ]
        ),
        "day": (
            group["day"]
        ),
        "time_window": (
            group[
                "time_window"
            ]
        ),
        "courses_involved": (
            group[
                "courses_involved"
            ]
        ),
        "best_fix": best_fix,
        "alternatives": (
            all_moves[:10]
        ),
        "important_note": (
            "These are timetable-based planning suggestions. "
            "They are not automatically applied because student "
            "conflicts are inferred without individual enrollment "
            "data. Suggestions marked 'requires_assignment' also "
            "need a room before they can be considered fully feasible."
        ),
    }


# ---------------------------------------------------------------------------
# ALL GROUPS
# ---------------------------------------------------------------------------


def resolve_all_student_conflict_groups(
    groups: list[dict],
    entries: list,
) -> list[dict]:
    resolutions = [
        resolve_student_conflict_group(
            group,
            entries,
        )
        for group in groups
    ]

    resolutions.sort(
        key=lambda item: (
            item[
                "best_fix"
            ]
            is None,
            (
                item[
                    "best_fix"
                ][
                    "room_status"
                ]
                == "requires_assignment"
                if item[
                    "best_fix"
                ]
                else True
            ),
            -(
                item[
                    "best_fix"
                ][
                    "score"
                ]
                if item[
                    "best_fix"
                ]
                else 0
            ),
            -item[
                "priority_score"
            ],
            item[
                "group_id"
            ],
        )
    )

    return resolutions