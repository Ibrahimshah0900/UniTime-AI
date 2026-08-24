from __future__ import annotations


def section_matches(assigned_section: str, timetable_section: str | None) -> bool:
    if timetable_section is None or not timetable_section.strip():
        return True
    timetable_sections = {
        part.strip().upper()
        for part in timetable_section.split(",")
        if part.strip()
    }
    return assigned_section.strip().upper() in timetable_sections


def semester_matches(assigned_semester: str, timetable_semester: str | None) -> bool:
    if timetable_semester is None or not timetable_semester.strip():
        return True
    return assigned_semester.strip().casefold() == timetable_semester.strip().casefold()
