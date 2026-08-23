from collections import Counter

from backend.models import TimetableEntry


def normalize(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip().lower()

    return value or None


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


def is_physical_room(
    room: str | None,
) -> bool:
    normalized = normalize(room)

    return normalized not in {
        None,
        "online",
    }


def is_lab_room(
    room: str | None,
) -> bool:
    normalized = normalize(room)

    return (
        normalized is not None
        and "lab" in normalized
    )


def room_is_compatible(
    room: str,
    class_type: str,
) -> bool:
    normalized_type = (
        normalize(class_type)
        or "lecture"
    )

    if normalized_type == "lab":
        return is_lab_room(room)

    return True


def get_known_rooms(
    entries: list[TimetableEntry],
) -> list[str]:
    rooms = {
        entry.room.strip()
        for entry in entries
        if is_physical_room(entry.room)
    }

    return sorted(
        rooms,
        key=str.lower,
    )


def room_is_available(
    room: str,
    day: str,
    start_time: str,
    end_time: str,
    entries: list[TimetableEntry],
    ignore_entry_id: int | None = None,
) -> bool:
    target_room = normalize(room)
    target_day = normalize(day)

    for entry in entries:
        if (
            ignore_entry_id is not None
            and entry.id == ignore_entry_id
        ):
            continue

        if normalize(entry.room) != target_room:
            continue

        if normalize(entry.day) != target_day:
            continue

        if times_overlap(
            start_time,
            end_time,
            entry.start_time,
            entry.end_time,
        ):
            return False

    return True


def room_usage_counts(
    entries: list[TimetableEntry],
) -> Counter:
    return Counter(
        normalize(entry.room)
        for entry in entries
        if is_physical_room(entry.room)
    )


def duration_minutes(
    start_time: str,
    end_time: str,
) -> int:
    start_hour, start_minute = map(
        int,
        start_time.split(":"),
    )

    end_hour, end_minute = map(
        int,
        end_time.split(":"),
    )

    return (
        (end_hour * 60 + end_minute)
        - (start_hour * 60 + start_minute)
    )


def score_room_move(
    target: TimetableEntry,
    candidate_room: str,
    usage_count: int,
) -> tuple[int, list[str]]:
    reasons: list[str] = []

    # Base score keeps room for both bonuses
    # and penalties without saturating at 100.
    score = 60

    # ---------------------------------------------------------
    # ROOM COMPATIBILITY
    # ---------------------------------------------------------

    if room_is_compatible(
        candidate_room,
        target.class_type,
    ):
        score += 15

        reasons.append(
            "Compatible room for this class type"
        )

    else:
        return (
            0,
            [
                "Room is not compatible with this class type"
            ],
        )

    # ---------------------------------------------------------
    # ROOM UTILIZATION
    # ---------------------------------------------------------

    if usage_count <= 12:
        score += 15

        reasons.append(
            "Low room utilization"
        )

    elif usage_count <= 18:
        score += 10

        reasons.append(
            "Moderate room utilization"
        )

    elif usage_count <= 24:
        score += 3

        reasons.append(
            "Higher room utilization"
        )

    else:
        score -= 5

        reasons.append(
            "Very high room utilization"
        )

    # ---------------------------------------------------------
    # CLASS DURATION
    # ---------------------------------------------------------

    duration = duration_minutes(
        target.start_time,
        target.end_time,
    )

    if duration <= 90:
        score += 10

        reasons.append(
            "Shorter class is easier to relocate"
        )

    elif duration <= 120:
        score += 6

        reasons.append(
            "Moderate-duration class"
        )

    else:
        score -= 8

        reasons.append(
            "Long class move is less preferred"
        )

    # ---------------------------------------------------------
    # LONG LAB PENALTY
    #
    # Moving a long practical/lab block is more disruptive.
    # ---------------------------------------------------------

    if (
        normalize(target.class_type) == "lab"
        and duration > 120
    ):
        score -= 5

        reasons.append(
            "Long lab block has additional relocation cost"
        )

    # Keep score within a clear UI range.
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


def suggest_rooms_for_entry(
    target: TimetableEntry,
    entries: list[TimetableEntry],
    limit: int = 5,
) -> list[dict]:
    known_rooms = get_known_rooms(
        entries
    )

    usage = room_usage_counts(
        entries
    )

    suggestions: list[dict] = []

    for room in known_rooms:
        if (
            normalize(room)
            == normalize(target.room)
        ):
            continue

        if not room_is_compatible(
            room,
            target.class_type,
        ):
            continue

        if not room_is_available(
            room=room,
            day=target.day,
            start_time=target.start_time,
            end_time=target.end_time,
            entries=entries,
            ignore_entry_id=target.id,
        ):
            continue

        usage_count = usage[
            normalize(room)
        ]

        score, reasons = score_room_move(
            target=target,
            candidate_room=room,
            usage_count=usage_count,
        )

        suggestions.append(
            {
                "room": room,
                "room_type": (
                    "lab"
                    if is_lab_room(room)
                    else "general"
                ),
                "weekly_usage_count": usage_count,
                "score": score,
                "reasons": reasons,
            }
        )

    suggestions.sort(
        key=lambda item: (
            -item["score"],
            item["weekly_usage_count"],
            item["room"].lower(),
        )
    )

    return suggestions[:limit]


def suggest_room_fixes_for_clash(
    clash: dict,
    entries: list[TimetableEntry],
    limit_per_entry: int = 5,
) -> dict:
    entry_lookup = {
        entry.id: entry
        for entry in entries
    }

    first = entry_lookup.get(
        clash["entry_1"]["id"]
    )

    second = entry_lookup.get(
        clash["entry_2"]["id"]
    )

    if first is None or second is None:
        return {
            "clash_type": clash.get("type"),
            "day": clash.get("day"),
            "reason": clash.get("reason"),
            "suggestions": [],
            "best_fix": None,
            "error": (
                "One or both timetable entries "
                "could not be found."
            ),
        }

    candidates: list[dict] = []
    ranked_moves: list[dict] = []

    for target in (
        first,
        second,
    ):
        rooms = suggest_rooms_for_entry(
            target=target,
            entries=entries,
            limit=limit_per_entry,
        )

        if not rooms:
            continue

        candidates.append(
            {
                "entry_id": target.id,
                "course_code": target.course_code,
                "course_name": target.course_name,
                "current_room": target.room,
                "day": target.day,
                "start_time": target.start_time,
                "end_time": target.end_time,
                "class_type": target.class_type,
                "alternative_rooms": rooms,
            }
        )

        for room in rooms:
            ranked_moves.append(
                {
                    "entry_id": target.id,
                    "course_code": target.course_code,
                    "course_name": target.course_name,
                    "from_room": target.room,
                    "to_room": room["room"],
                    "day": target.day,
                    "start_time": target.start_time,
                    "end_time": target.end_time,
                    "score": room["score"],
                    "weekly_usage_count": (
                        room["weekly_usage_count"]
                    ),
                    "reasons": [
                        (
                            "Room is free for the "
                            "complete class period"
                        ),
                        *room["reasons"],
                    ],
                }
            )

    ranked_moves.sort(
        key=lambda item: (
            -item["score"],
            duration_minutes(
                item["start_time"],
                item["end_time"],
            ),
            item["weekly_usage_count"],
            item["to_room"].lower(),
        )
    )

    best_fix = (
        ranked_moves[0]
        if ranked_moves
        else None
    )

    return {
        "clash_type": clash.get("type"),
        "day": clash.get("day"),
        "reason": clash.get("reason"),
        "suggestions": candidates,
        "best_fix": best_fix,
    }