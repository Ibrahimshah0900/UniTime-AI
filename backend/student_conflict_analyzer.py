from __future__ import annotations

import re
from itertools import combinations

from backend.models import TimetableEntry


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

COMMON_PREFIXES = {
    "MT",
    "SS",
    "MG",
    "NS",
}


# ---------------------------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------------------------


def normalize(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip().upper()

    return cleaned or None


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


def shared_sections(
    first: TimetableEntry,
    second: TimetableEntry,
) -> set[str]:
    return (
        parse_sections(first.section)
        & parse_sections(second.section)
    )


# ---------------------------------------------------------------------------
# COURSE CODE HELPERS
# ---------------------------------------------------------------------------


def course_prefix(
    course_code: str | None,
) -> str | None:
    if not course_code:
        return None

    match = re.match(
        r"([A-Za-z]+)",
        course_code.strip(),
    )

    if not match:
        return None

    return match.group(1).upper()


def extract_course_levels(
    course_code: str | None,
) -> set[int]:
    """
    Extract broad academic levels from course codes.

    Examples:
        CS106       -> {1}
        CS210       -> {2}
        CS385       -> {3}
        CS432       -> {4}
        MT100/MT110 -> {1}

    IMPORTANT:
    This is NOT semester inference.

    Level 2 simply means a 2xx course. It does not claim
    that the course belongs to semester 3, 4, or any other
    particular semester.
    """

    if not course_code:
        return set()

    codes = course_code.upper().split("/")

    levels: set[int] = set()

    for code in codes:
        match = re.search(
            r"(\d{3})",
            code,
        )

        if not match:
            continue

        numeric_code = match.group(1)

        level = int(
            numeric_code[0]
        )

        if 1 <= level <= 9:
            levels.add(level)

    return levels


def same_course_level(
    first: TimetableEntry,
    second: TimetableEntry,
) -> bool:
    first_levels = extract_course_levels(
        first.course_code
    )

    second_levels = extract_course_levels(
        second.course_code
    )

    if (
        not first_levels
        or not second_levels
    ):
        return False

    return bool(
        first_levels
        & second_levels
    )


def same_course(
    first: TimetableEntry,
    second: TimetableEntry,
) -> bool:
    first_code = normalize(
        first.course_code
    )

    second_code = normalize(
        second.course_code
    )

    return (
        first_code is not None
        and second_code is not None
        and first_code == second_code
    )


def is_common_course(
    entry: TimetableEntry,
) -> bool:
    prefix = course_prefix(
        entry.course_code
    )

    return (
        prefix in COMMON_PREFIXES
    )


# ---------------------------------------------------------------------------
# SEMESTER HELPERS
# ---------------------------------------------------------------------------


def semesters_match(
    first: TimetableEntry,
    second: TimetableEntry,
) -> bool:
    first_semester = normalize(
        first.semester
    )

    second_semester = normalize(
        second.semester
    )

    return (
        first_semester is not None
        and second_semester is not None
        and first_semester == second_semester
    )


def both_semesters_known(
    first: TimetableEntry,
    second: TimetableEntry,
) -> bool:
    return (
        normalize(first.semester) is not None
        and normalize(second.semester) is not None
    )


# ---------------------------------------------------------------------------
# SERIALIZATION
# ---------------------------------------------------------------------------


def build_entry_summary(
    entry: TimetableEntry,
) -> dict:
    return {
        "id": entry.id,
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "course_levels": sorted(
            extract_course_levels(
                entry.course_code
            )
        ),
        "semester": entry.semester,
        "section": entry.section,
        "faculty": entry.faculty,
        "room": entry.room,
        "day": entry.day,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "class_type": entry.class_type,
        "raw_text": entry.raw_text,
    }


# ---------------------------------------------------------------------------
# CONFLICT CLASSIFICATION
# ---------------------------------------------------------------------------


def classify_student_conflict(
    first: TimetableEntry,
    second: TimetableEntry,
) -> dict | None:
    if not times_overlap(
        first,
        second,
    ):
        return None

    overlap_sections = shared_sections(
        first,
        second,
    )

    same_sem = semesters_match(
        first,
        second,
    )

    semesters_known = both_semesters_known(
        first,
        second,
    )

    same_level = same_course_level(
        first,
        second,
    )

    same_code = same_course(
        first,
        second,
    )

    evidence: list[str] = []

    limitations: list[str] = []

    risk_level: str | None = None

    risk_type: str | None = None

    score = 0

    # ------------------------------------------------------------------
    # CONFIRMED
    #
    # Strongest timetable-only evidence:
    # same explicitly known semester + shared section + overlap.
    # ------------------------------------------------------------------

    if (
        same_sem
        and overlap_sections
    ):
        risk_level = "confirmed"

        risk_type = (
            "same_semester_section_overlap"
        )

        score = 95

        evidence.append(
            "Both classes belong to the same explicitly known semester."
        )

        evidence.append(
            "Both classes include the same section(s): "
            + ", ".join(
                sorted(overlap_sections)
            )
        )

    # ------------------------------------------------------------------
    # PROBABLE
    #
    # Semester is unavailable, but:
    #
    # - classes overlap
    # - they share section labels
    # - they are from the same broad 1xx/2xx/3xx/4xx course level
    #
    # This is much stronger than Section A alone.
    # ------------------------------------------------------------------

    elif (
        overlap_sections
        and same_level
        and not semesters_known
    ):
        risk_level = "probable"

        risk_type = (
            "same_level_section_overlap"
        )

        score = 72

        first_levels = sorted(
            extract_course_levels(
                first.course_code
            )
        )

        second_levels = sorted(
            extract_course_levels(
                second.course_code
            )
        )

        evidence.append(
            "The classes overlap and share section(s): "
            + ", ".join(
                sorted(overlap_sections)
            )
        )

        evidence.append(
            "Both courses belong to the same broad academic "
            "course level."
        )

        evidence.append(
            f"Detected levels: "
            f"{first.course_code}={first_levels}, "
            f"{second.course_code}={second_levels}."
        )

        limitations.append(
            "Course level is inferred only from the course-number "
            "range, such as 2xx or 3xx. It is not semester inference."
        )

        limitations.append(
            "Student enrollment data is unavailable, so affected "
            "students cannot be confirmed."
        )

    # ------------------------------------------------------------------
    # POSSIBLE: SAME COURSE
    #
    # Parallel sections of the exact same course overlap.
    # This may be completely intentional, so we keep it low confidence.
    # ------------------------------------------------------------------

    elif same_code:
        risk_level = "possible"

        risk_type = (
            "same_course_parallel_overlap"
        )

        score = 42

        evidence.append(
            "Two overlapping timetable entries have the same course code."
        )

        if overlap_sections:
            evidence.append(
                "The entries also share section label(s): "
                + ", ".join(
                    sorted(overlap_sections)
                )
            )

        limitations.append(
            "Parallel sections of the same course may intentionally "
            "run at the same time."
        )

        limitations.append(
            "Enrollment data is required to determine whether the "
            "same student is registered in both entries."
        )

    # ------------------------------------------------------------------
    # POSSIBLE: COMMON COURSE + SAME LEVEL + SHARED SECTION
    #
    # Slightly weaker signal retained for common university courses.
    # ------------------------------------------------------------------

    elif (
        overlap_sections
        and same_level
        and (
            is_common_course(first)
            or is_common_course(second)
        )
    ):
        risk_level = "possible"

        risk_type = (
            "common_course_cohort_risk"
        )

        score = 35

        evidence.append(
            "The classes share a section label and broad course level."
        )

        evidence.append(
            "At least one class appears to be a common/shared course."
        )

        limitations.append(
            "No direct student enrollment information is available."
        )

    # ------------------------------------------------------------------
    # DO NOT FLAG
    #
    # Important:
    #
    # Section A vs Section A by itself is NOT enough.
    #
    # CS106(A) and CS385(A), for example, may represent completely
    # different cohorts. This deliberately removes those noisy results.
    # ------------------------------------------------------------------

    if risk_level is None:
        return None

    return {
        "type": "student_conflict_risk",
        "risk_type": risk_type,
        "risk_level": risk_level,
        "score": score,
        "day": first.day,
        "overlap": {
            "entry_1_time": (
                f"{first.start_time}-{first.end_time}"
            ),
            "entry_2_time": (
                f"{second.start_time}-{second.end_time}"
            ),
        },
        "shared_sections": sorted(
            overlap_sections
        ),
        "same_course_level": (
            same_level
        ),
        "evidence": evidence,
        "limitations": limitations,
        "entry_1": build_entry_summary(
            first
        ),
        "entry_2": build_entry_summary(
            second
        ),
    }


# ---------------------------------------------------------------------------
# FULL ANALYSIS
# ---------------------------------------------------------------------------


def analyze_student_conflicts(
    entries: list[TimetableEntry],
) -> list[dict]:
    conflicts: list[dict] = []

    # Special events are not ordinary student course entries.
    course_entries = [
        entry
        for entry in entries
        if entry.entry_kind == "course"
    ]

    for first, second in combinations(
        course_entries,
        2,
    ):
        result = classify_student_conflict(
            first,
            second,
        )

        if result is not None:
            conflicts.append(
                result
            )

    priority = {
        "confirmed": 0,
        "probable": 1,
        "possible": 2,
    }

    conflicts.sort(
        key=lambda item: (
            priority[
                item["risk_level"]
            ],
            -item["score"],
            item["day"],
            item["entry_1"]["start_time"],
            item["entry_1"]["id"],
            item["entry_2"]["id"],
        )
    )

    return conflicts


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------


def summarize_student_conflicts(
    conflicts: list[dict],
) -> dict:
    confirmed = sum(
        1
        for conflict in conflicts
        if conflict["risk_level"]
        == "confirmed"
    )

    probable = sum(
        1
        for conflict in conflicts
        if conflict["risk_level"]
        == "probable"
    )

    possible = sum(
        1
        for conflict in conflicts
        if conflict["risk_level"]
        == "possible"
    )

    return {
        "total": len(conflicts),
        "confirmed": confirmed,
        "probable": probable,
        "possible": possible,
        "important_note": (
            "Course level is inferred from course-number ranges "
            "(for example 2xx or 3xx) only. It is not treated as "
            "semester information. Student enrollment data is not "
            "available, so probable and possible results are risk "
            "signals rather than confirmed affected-student counts."
        ),
    }