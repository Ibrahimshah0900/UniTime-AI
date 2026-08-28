from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    CourseOffering,
    FacultyAvailabilityWindow,
    FacultyClassAssignment,
    User,
)
from backend.schedule_matching import normalize_course_code, normalize_section
from backend.scheduling_policy import (
    DEFAULT_SCHEDULING_POLICY,
    INSTITUTIONAL_POLICY_VERSION,
    allowed_days_for,
    parse_semester_number,
)


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _times_overlap(
    first_start: str,
    first_end: str,
    second_start: str,
    second_end: str,
) -> bool:
    return first_start < second_end and second_start < first_end


def subject_identity(
    course_code: str | None,
    semester: object,
    section: str | None,
) -> tuple[str, int, str] | None:
    code = normalize_course_code(course_code)
    semester_number = parse_semester_number(semester)
    normalized_section = normalize_section(section)
    if not code or semester_number is None or not normalized_section:
        return None
    return (code.upper(), semester_number, normalized_section.upper())


def component_identity(
    course_code: str | None,
    semester: object,
    section: str | None,
    class_type: str | None,
) -> tuple[str, int, str, str] | None:
    subject = subject_identity(course_code, semester, section)
    kind = _normalize(class_type)
    if subject is None or kind not in {"lecture", "lab"}:
        return None
    return (*subject, kind)


@dataclass(frozen=True)
class InstitutionalConstraintContext:
    term_id: int
    offerings_by_component: dict[
        tuple[str, int, str, str],
        CourseOffering,
    ]
    assignments_by_subject: dict[
        tuple[str, int, str],
        tuple[FacultyClassAssignment, ...],
    ]
    faculty_by_id: dict[int, User]
    availability_by_faculty: dict[
        int,
        tuple[FacultyAvailabilityWindow, ...],
    ]
    fingerprint: str


def build_institutional_constraint_context(
    db: Session,
    *,
    term_id: int,
) -> InstitutionalConstraintContext:
    offerings = list(
        db.scalars(
            select(CourseOffering)
            .where(CourseOffering.term_id == term_id)
            .order_by(CourseOffering.id)
        ).all()
    )
    assignments = list(
        db.scalars(
            select(FacultyClassAssignment)
            .where(FacultyClassAssignment.term_id == term_id)
            .order_by(FacultyClassAssignment.id)
        ).all()
    )
    faculty_ids = sorted(
        {assignment.faculty_user_id for assignment in assignments}
    )
    faculty_rows = (
        list(
            db.scalars(
                select(User)
                .where(User.id.in_(faculty_ids))
                .order_by(User.id)
            ).all()
        )
        if faculty_ids
        else []
    )
    availability = (
        list(
            db.scalars(
                select(FacultyAvailabilityWindow)
                .where(
                    FacultyAvailabilityWindow.term_id == term_id,
                    FacultyAvailabilityWindow.faculty_user_id.in_(faculty_ids),
                )
                .order_by(
                    FacultyAvailabilityWindow.faculty_user_id,
                    FacultyAvailabilityWindow.day,
                    FacultyAvailabilityWindow.start_time,
                    FacultyAvailabilityWindow.end_time,
                    FacultyAvailabilityWindow.id,
                )
            ).all()
        )
        if faculty_ids
        else []
    )

    offerings_by_component: dict[
        tuple[str, int, str, str],
        CourseOffering,
    ] = {}
    for offering in offerings:
        key = component_identity(
            offering.course_code,
            offering.semester,
            offering.section,
            offering.class_type,
        )
        if key is not None:
            offerings_by_component[key] = offering

    assignment_lists: dict[
        tuple[str, int, str],
        list[FacultyClassAssignment],
    ] = {}
    for assignment in assignments:
        key = subject_identity(
            assignment.course_code,
            assignment.semester,
            assignment.section,
        )
        if key is not None:
            assignment_lists.setdefault(key, []).append(assignment)

    faculty_by_id = {faculty.id: faculty for faculty in faculty_rows}
    availability_lists: dict[int, list[FacultyAvailabilityWindow]] = {}
    for window in availability:
        availability_lists.setdefault(window.faculty_user_id, []).append(window)

    canonical = {
        "policy_version": INSTITUTIONAL_POLICY_VERSION,
        "term_id": term_id,
        "offerings": [
            [
                item.id,
                item.course_code,
                item.course_name,
                item.semester,
                item.section,
                item.class_type,
                item.duration_minutes,
                item.room,
            ]
            for item in offerings
        ],
        "assignments": [
            [
                item.id,
                item.faculty_user_id,
                item.course_code,
                item.semester,
                item.section,
            ]
            for item in assignments
        ],
        "faculty": [
            [
                faculty.id,
                faculty.full_name,
                faculty.email,
                faculty.is_active,
            ]
            for faculty in faculty_rows
        ],
        "availability": [
            [
                window.id,
                window.faculty_user_id,
                window.day,
                window.start_time,
                window.end_time,
            ]
            for window in availability
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return InstitutionalConstraintContext(
        term_id=term_id,
        offerings_by_component=offerings_by_component,
        assignments_by_subject={
            key: tuple(items)
            for key, items in assignment_lists.items()
        },
        faculty_by_id=faculty_by_id,
        availability_by_faculty={
            faculty_id: tuple(items)
            for faculty_id, items in availability_lists.items()
        },
        fingerprint=fingerprint,
    )


def _faculty_for_entry(
    context: InstitutionalConstraintContext,
    entry,
) -> tuple[bool, tuple[FacultyClassAssignment, ...], User | None]:
    component = component_identity(
        getattr(entry, "course_code", None),
        getattr(entry, "semester", None),
        getattr(entry, "section", None),
        getattr(entry, "class_type", None),
    )
    structured = (
        component is not None
        and component in context.offerings_by_component
    )
    subject = subject_identity(
        getattr(entry, "course_code", None),
        getattr(entry, "semester", None),
        getattr(entry, "section", None),
    )
    assignments = (
        context.assignments_by_subject.get(subject, ())
        if subject is not None
        else ()
    )
    faculty = (
        context.faculty_by_id.get(assignments[0].faculty_user_id)
        if len(assignments) == 1
        else None
    )
    return structured, assignments, faculty


def _faculty_display_matches(value: str | None, faculty: User) -> bool:
    normalized = _normalize(value)
    if normalized is None:
        return False
    identities = {
        _normalize(faculty.full_name),
        _normalize(faculty.email),
    }
    return normalized in identities


def _availability_covers(
    windows: Iterable[FacultyAvailabilityWindow],
    *,
    day: str,
    start_time: str,
    end_time: str,
) -> bool:
    return any(
        window.day == day
        and window.start_time <= start_time
        and end_time <= window.end_time
        for window in windows
    )


def validate_institutional_destination(
    context: InstitutionalConstraintContext,
    entry,
    *,
    day: str,
    start_time: str,
    end_time: str,
    entries: Iterable,
    strict_managed: bool = False,
) -> dict:
    hard_failures: list[str] = list(
        DEFAULT_SCHEDULING_POLICY.validate_slot(
            day=day,
            start_time=start_time,
            end_time=end_time,
        )
    )
    missing_data: list[str] = []

    semester_number = parse_semester_number(
        getattr(entry, "semester", None)
    )
    class_type = _normalize(getattr(entry, "class_type", None))
    if (
        semester_number is not None
        and class_type in {"lecture", "lab"}
    ):
        allowed_days = allowed_days_for(
            semester_number,
            class_type,
        )
        if day not in allowed_days:
            hard_failures.append(
                f"Semester {semester_number} {class_type} sessions "
                f"must be scheduled on {', '.join(allowed_days)}."
            )

    for other in entries:
        if getattr(other, "id", None) == getattr(entry, "id", None):
            continue
        if getattr(other, "entry_kind", "course") != "course":
            continue
        if _normalize(getattr(other, "day", None)) != _normalize(day):
            continue
        if not _times_overlap(
            start_time,
            end_time,
            other.start_time,
            other.end_time,
        ):
            continue

        other_semester = parse_semester_number(
            getattr(other, "semester", None)
        )
        if (
            semester_number is not None
            and other_semester == semester_number
        ):
            hard_failures.append(
                f"Semester {semester_number} already has an overlapping "
                "subject in this slot."
            )

    structured, assignments, faculty = _faculty_for_entry(
        context,
        entry,
    )
    availability_configured = False
    faculty_user_id: int | None = None

    if structured:
        if len(assignments) == 0:
            missing_data.append(
                "Managed course offering has no faculty allocation."
            )
        elif len(assignments) > 1:
            missing_data.append(
                "Managed course offering has ambiguous multiple faculty allocations."
            )
        elif faculty is None or not faculty.is_active or faculty.role != "faculty":
            missing_data.append(
                "Managed course offering does not resolve to one active faculty account."
            )
        else:
            faculty_user_id = faculty.id
            windows = context.availability_by_faculty.get(
                faculty.id,
                (),
            )
            availability_configured = bool(windows)
            if not windows:
                missing_data.append(
                    "Assigned faculty has no true availability configured for this term."
                )
            elif not _availability_covers(
                windows,
                day=day,
                start_time=start_time,
                end_time=end_time,
            ):
                hard_failures.append(
                    "Destination falls outside the assigned faculty member's "
                    "declared availability."
                )

            for other in entries:
                if getattr(other, "id", None) == getattr(entry, "id", None):
                    continue
                if _normalize(getattr(other, "day", None)) != _normalize(day):
                    continue
                if not _times_overlap(
                    start_time,
                    end_time,
                    other.start_time,
                    other.end_time,
                ):
                    continue
                (
                    _other_structured,
                    other_assignments,
                    other_faculty,
                ) = _faculty_for_entry(context, other)
                if (
                    len(other_assignments) == 1
                    and other_faculty is not None
                    and other_faculty.id == faculty.id
                ):
                    hard_failures.append(
                        "Destination creates a structured faculty clash."
                    )
                    continue
                if _faculty_display_matches(
                    getattr(other, "faculty", None),
                    faculty,
                ):
                    hard_failures.append(
                        "Destination creates a faculty clash."
                    )

    room = _normalize(getattr(entry, "room", None))
    if structured and room is None:
        missing_data.append(
            "Managed course offering has no room assigned."
        )
    if room not in {None, "online"}:
        for other in entries:
            if getattr(other, "id", None) == getattr(entry, "id", None):
                continue
            if _normalize(getattr(other, "day", None)) != _normalize(day):
                continue
            if _normalize(getattr(other, "room", None)) != room:
                continue
            if _times_overlap(
                start_time,
                end_time,
                other.start_time,
                other.end_time,
            ):
                hard_failures.append(
                    "Destination creates a physical room clash."
                )

    hard_failures = list(dict.fromkeys(hard_failures))
    missing_data = list(dict.fromkeys(missing_data))

    if strict_managed and structured and missing_data:
        hard_failures.extend(
            f"Managed scheduling metadata incomplete: {item}"
            for item in missing_data
        )
        hard_failures = list(dict.fromkeys(hard_failures))

    return {
        "hard_failures": hard_failures,
        "missing_data": missing_data,
        "structured": structured,
        "faculty_user_id": faculty_user_id,
        "faculty_name": faculty.full_name if faculty is not None else None,
        "availability_configured": availability_configured,
    }
