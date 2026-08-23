from __future__ import annotations

from collections import defaultdict
from typing import Any


RISK_PRIORITY = {
    "confirmed": 3,
    "probable": 2,
    "possible": 1,
}


def entry_key(
    entry: dict,
) -> int:
    return int(entry["id"])


def conflict_time_key(
    conflict: dict,
) -> tuple:
    """
    Groups conflicts occurring in the same broad timetable window.

    We use the actual pair start/end values so extended classes
    such as AI232 10:00-13:00 can still participate correctly.
    """

    entry_1 = conflict["entry_1"]
    entry_2 = conflict["entry_2"]

    starts = sorted(
        [
            entry_1["start_time"],
            entry_2["start_time"],
        ]
    )

    ends = sorted(
        [
            entry_1["end_time"],
            entry_2["end_time"],
        ]
    )

    return (
        conflict["day"],
        starts[0],
        ends[-1],
    )


def get_conflict_level(
    conflict: dict,
) -> int | None:
    levels_1 = set(
        conflict["entry_1"].get(
            "course_levels",
            [],
        )
    )

    levels_2 = set(
        conflict["entry_2"].get(
            "course_levels",
            [],
        )
    )

    shared = (
        levels_1
        & levels_2
    )

    if len(shared) == 1:
        return next(
            iter(shared)
        )

    return None


def get_conflict_sections(
    conflict: dict,
) -> set[str]:
    return {
        section.upper()
        for section in conflict.get(
            "shared_sections",
            [],
        )
        if section
    }


def conflicts_belong_together(
    first: dict,
    second: dict,
) -> bool:
    """
    Decide whether two pairwise risks belong in one actionable group.

    Requirements:
    - same day
    - overlapping overall time window
    - same inferred course level where available
    - at least one shared section label
    - pairwise records are connected through a timetable entry
      OR through the same section/level/time cohort

    This is still heuristic grouping, not enrollment confirmation.
    """

    if first["day"] != second["day"]:
        return False

    first_level = get_conflict_level(
        first
    )

    second_level = get_conflict_level(
        second
    )

    if (
        first_level is not None
        and second_level is not None
        and first_level != second_level
    ):
        return False

    first_sections = (
        get_conflict_sections(
            first
        )
    )

    second_sections = (
        get_conflict_sections(
            second
        )
    )

    if not (
        first_sections
        & second_sections
    ):
        return False

    first_ids = {
        entry_key(
            first["entry_1"]
        ),
        entry_key(
            first["entry_2"]
        ),
    }

    second_ids = {
        entry_key(
            second["entry_1"]
        ),
        entry_key(
            second["entry_2"]
        ),
    }

    first_start = min(
        first["entry_1"]["start_time"],
        first["entry_2"]["start_time"],
    )

    first_end = max(
        first["entry_1"]["end_time"],
        first["entry_2"]["end_time"],
    )

    second_start = min(
        second["entry_1"]["start_time"],
        second["entry_2"]["start_time"],
    )

    second_end = max(
        second["entry_1"]["end_time"],
        second["entry_2"]["end_time"],
    )

    time_overlap = (
        first_start < second_end
        and second_start < first_end
    )

    if not time_overlap:
        return False

    if first_ids & second_ids:
        return True

    # Also allow grouping of separate pairwise conflicts that clearly
    # belong to the same inferred cohort/time block.
    return (
        first_level == second_level
        and bool(
            first_sections
            & second_sections
        )
    )


def build_connected_components(
    conflicts: list[dict],
) -> list[list[dict]]:
    """
    Build connected components over the pairwise risk graph.
    """

    if not conflicts:
        return []

    visited: set[int] = set()

    components: list[
        list[dict]
    ] = []

    for start_index in range(
        len(conflicts)
    ):
        if start_index in visited:
            continue

        stack = [
            start_index
        ]

        visited.add(
            start_index
        )

        component: list[
            dict
        ] = []

        while stack:
            current_index = (
                stack.pop()
            )

            current = conflicts[
                current_index
            ]

            component.append(
                current
            )

            for other_index in range(
                len(conflicts)
            ):
                if other_index in visited:
                    continue

                other = conflicts[
                    other_index
                ]

                if conflicts_belong_together(
                    current,
                    other,
                ):
                    visited.add(
                        other_index
                    )

                    stack.append(
                        other_index
                    )

        components.append(
            component
        )

    return components


def strongest_risk_level(
    conflicts: list[dict],
) -> str:
    return max(
        (
            conflict[
                "risk_level"
            ]
            for conflict in conflicts
        ),
        key=lambda level: (
            RISK_PRIORITY.get(
                level,
                0,
            )
        ),
    )


def group_score(
    conflicts: list[dict],
) -> int:
    """
    Create a group-level score.

    The score represents review priority, not probability
    that a specific student is affected.
    """

    highest_pair_score = max(
        conflict.get(
            "score",
            0,
        )
        for conflict in conflicts
    )

    entry_ids: set[int] = set()

    for conflict in conflicts:
        entry_ids.add(
            entry_key(
                conflict[
                    "entry_1"
                ]
            )
        )

        entry_ids.add(
            entry_key(
                conflict[
                    "entry_2"
                ]
            )
        )

    size_bonus = min(
        max(
            len(entry_ids) - 2,
            0,
        )
        * 4,
        16,
    )

    return min(
        highest_pair_score
        + size_bonus,
        100,
    )


def build_group(
    group_id: int,
    conflicts: list[dict],
) -> dict:
    entries: dict[
        int,
        dict,
    ] = {}

    sections: set[str] = set()

    levels: set[int] = set()

    evidence: set[str] = set()

    limitations: set[str] = set()

    start_times: list[str] = []
    end_times: list[str] = []

    for conflict in conflicts:
        for entry_name in (
            "entry_1",
            "entry_2",
        ):
            entry = conflict[
                entry_name
            ]

            entries[
                entry_key(entry)
            ] = entry

            start_times.append(
                entry[
                    "start_time"
                ]
            )

            end_times.append(
                entry[
                    "end_time"
                ]
            )

        sections.update(
            get_conflict_sections(
                conflict
            )
        )

        level = get_conflict_level(
            conflict
        )

        if level is not None:
            levels.add(
                level
            )

        evidence.update(
            conflict.get(
                "evidence",
                [],
            )
        )

        limitations.update(
            conflict.get(
                "limitations",
                [],
            )
        )

    ordered_entries = sorted(
        entries.values(),
        key=lambda entry: (
            entry[
                "start_time"
            ],
            entry.get(
                "course_code"
            )
            or "",
            entry["id"],
        ),
    )

    risk_level = strongest_risk_level(
        conflicts
    )

    score = group_score(
        conflicts
    )

    return {
        "group_id": group_id,
        "type": "student_conflict_group",
        "risk_level": risk_level,
        "priority_score": score,
        "day": conflicts[0][
            "day"
        ],
        "time_window": {
            "start_time": min(
                start_times
            ),
            "end_time": max(
                end_times
            ),
        },
        "course_levels": sorted(
            levels
        ),
        "shared_sections": sorted(
            sections
        ),
        "courses_involved": len(
            ordered_entries
        ),
        "pairwise_risks": len(
            conflicts
        ),
        "entries": ordered_entries,
        "evidence": sorted(
            evidence
        ),
        "limitations": sorted(
            limitations
        ),
        "action": (
            "Review this timetable block as one cohort-level "
            "scheduling problem rather than resolving each "
            "pairwise warning independently."
        ),
    }


def build_student_conflict_groups(
    conflicts: list[dict],
) -> list[dict]:
    """
    Convert pairwise student-risk signals into reviewable groups.
    """

    relevant_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.get(
            "risk_level"
        )
        in {
            "confirmed",
            "probable",
        }
    ]

    components = (
        build_connected_components(
            relevant_conflicts
        )
    )

    groups = [
        build_group(
            group_id=index,
            conflicts=component,
        )
        for index, component
        in enumerate(
            components,
            start=1,
        )
    ]

    groups.sort(
        key=lambda group: (
            -RISK_PRIORITY.get(
                group[
                    "risk_level"
                ],
                0,
            ),
            -group[
                "priority_score"
            ],
            -group[
                "courses_involved"
            ],
            group[
                "day"
            ],
            group[
                "time_window"
            ][
                "start_time"
            ],
        )
    )

    # Re-number after sorting.
    for index, group in enumerate(
        groups,
        start=1,
    ):
        group[
            "group_id"
        ] = index

    return groups


def summarize_student_conflict_groups(
    groups: list[dict],
) -> dict:
    confirmed = sum(
        1
        for group in groups
        if group[
            "risk_level"
        ]
        == "confirmed"
    )

    probable = sum(
        1
        for group in groups
        if group[
            "risk_level"
        ]
        == "probable"
    )

    courses_involved = {
        entry["id"]
        for group in groups
        for entry in group[
            "entries"
        ]
    }

    return {
        "total_groups": len(
            groups
        ),
        "confirmed_groups": (
            confirmed
        ),
        "probable_groups": (
            probable
        ),
        "unique_timetable_entries_involved": len(
            courses_involved
        ),
        "important_note": (
            "These are grouped timetable-based cohort risks. "
            "They do not prove that individual students are "
            "enrolled in every course within a group."
        ),
    }