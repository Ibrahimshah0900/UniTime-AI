from backend.models import TimetableEntry


def normalize(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip().lower()

    return value or None


def times_overlap(
    first: TimetableEntry,
    second: TimetableEntry,
) -> bool:
    if normalize(first.day) != normalize(second.day):
        return False

    return (
        first.start_time < second.end_time
        and second.start_time < first.end_time
    )


def parse_sections(
    value: str | None,
) -> set[str]:
    if not value:
        return set()

    return {
        section.strip().upper()
        for section in value.split(",")
        if section.strip()
    }


def is_real_faculty(
    value: str | None,
) -> bool:
    normalized = normalize(value)

    if normalized is None:
        return False

    return normalized not in {
        "tba",
        "none",
        "n/a",
        "na",
    }


def is_physical_room(
    value: str | None,
) -> bool:
    normalized = normalize(value)

    if normalized is None:
        return False

    # Many online classes can run simultaneously.
    if normalized == "online":
        return False

    return True


def create_clash(
    clash_type: str,
    first: TimetableEntry,
    second: TimetableEntry,
    reason: str,
    severity: str = "critical",
) -> dict:
    return {
        "type": clash_type,
        "severity": severity,
        "day": first.day,
        "overlap": {
            "entry_1_time": (
                f"{first.start_time}-{first.end_time}"
            ),
            "entry_2_time": (
                f"{second.start_time}-{second.end_time}"
            ),
        },
        "reason": reason,
        "entry_1": {
            "id": first.id,
            "entry_kind": first.entry_kind,
            "course_code": first.course_code,
            "course_name": first.course_name,
            "semester": first.semester,
            "section": first.section,
            "faculty": first.faculty,
            "room": first.room,
            "start_time": first.start_time,
            "end_time": first.end_time,
            "raw_text": first.raw_text,
        },
        "entry_2": {
            "id": second.id,
            "entry_kind": second.entry_kind,
            "course_code": second.course_code,
            "course_name": second.course_name,
            "semester": second.semester,
            "section": second.section,
            "faculty": second.faculty,
            "room": second.room,
            "start_time": second.start_time,
            "end_time": second.end_time,
            "raw_text": second.raw_text,
        },
    }


def detect_clashes(
    entries: list[TimetableEntry],
) -> list[dict]:
    clashes: list[dict] = []

    for index, first in enumerate(entries):
        for second in entries[index + 1 :]:

            if not times_overlap(first, second):
                continue

            # -------------------------------------------------
            # ROOM CLASH
            # -------------------------------------------------

            if (
                is_physical_room(first.room)
                and is_physical_room(second.room)
                and normalize(first.room)
                == normalize(second.room)
            ):
                clashes.append(
                    create_clash(
                        clash_type="room",
                        first=first,
                        second=second,
                        reason=(
                            f"Room {first.room} is assigned "
                            "to two overlapping timetable "
                            "entries."
                        ),
                    )
                )

            # -------------------------------------------------
            # FACULTY CLASH
            # -------------------------------------------------

            if (
                is_real_faculty(first.faculty)
                and is_real_faculty(second.faculty)
                and normalize(first.faculty)
                == normalize(second.faculty)
            ):
                clashes.append(
                    create_clash(
                        clash_type="faculty",
                        first=first,
                        second=second,
                        reason=(
                            f"Faculty {first.faculty} is "
                            "assigned to two overlapping "
                            "timetable entries."
                        ),
                    )
                )

            # -------------------------------------------------
            # SECTION CLASH
            #
            # Only evaluate this when semester information
            # actually exists. We deliberately do NOT invent
            # semesters from course codes.
            # -------------------------------------------------

            first_semester = normalize(first.semester)
            second_semester = normalize(second.semester)

            if (
                first_semester
                and second_semester
                and first_semester == second_semester
            ):
                first_sections = parse_sections(
                    first.section
                )

                second_sections = parse_sections(
                    second.section
                )

                shared_sections = (
                    first_sections
                    & second_sections
                )

                if shared_sections:
                    section_text = ", ".join(
                        sorted(shared_sections)
                    )

                    clashes.append(
                        create_clash(
                            clash_type="section",
                            first=first,
                            second=second,
                            reason=(
                                f"Semester {first.semester}, "
                                f"section(s) {section_text} "
                                "have overlapping classes."
                            ),
                        )
                    )

    return clashes