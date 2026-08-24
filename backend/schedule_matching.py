from __future__ import annotations


DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def normalize_course_code(value: str) -> str:
    return " ".join(value.split()).upper()


def normalize_section(value: str) -> str:
    normalized_parts = [
        " ".join(part.split()).upper()
        for part in value.split(",")
        if part.strip()
    ]
    return ",".join(normalized_parts)


def normalize_semester(value: str) -> str:
    return " ".join(value.split()).title()


def timetable_sort_key(entry) -> tuple[int, str, str, int]:
    return (
        DAY_ORDER.get(entry.day, len(DAY_ORDER)),
        entry.start_time,
        entry.course_code or entry.course_name or "",
        entry.id or 0,
    )


def section_matches(assigned_section: str, timetable_section: str | None) -> bool:
    if timetable_section is None or not timetable_section.strip():
        return True
    timetable_sections = {
        normalize_section(part)
        for part in timetable_section.split(",")
        if part.strip()
    }
    return normalize_section(assigned_section) in timetable_sections


def semester_matches(assigned_semester: str, timetable_semester: str | None) -> bool:
    if timetable_semester is None or not timetable_semester.strip():
        return True
    return normalize_semester(assigned_semester) == normalize_semester(timetable_semester)
