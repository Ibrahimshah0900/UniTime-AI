from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.enrollment_schemas import EnrollmentCreate
from backend.models import StudentEnrollment, TimetableEntry
from backend.learning_event_service import record_learning_event, stable_learning_key
from backend.schedule_matching import (
    normalize_section,
    section_matches,
    semester_matches,
    timetable_sort_key,
)
from backend.student_conflict_analyzer import times_overlap
from backend.term_service import get_active_term, require_active_term_id


def list_student_enrollments(
    db: Session,
    user_id: int,
    *,
    term_id: int | None = None,
) -> list[StudentEnrollment]:
    selected_term_id = term_id or get_active_term(db).id
    statement = (
        select(StudentEnrollment)
        .where(
            StudentEnrollment.user_id == user_id,
            StudentEnrollment.term_id == selected_term_id,
        )
        .order_by(
            StudentEnrollment.semester,
            StudentEnrollment.course_code,
            StudentEnrollment.section,
        )
    )
    return list(db.scalars(statement).all())


def _find_existing_enrollment(
    db: Session,
    *,
    user_id: int,
    term_id: int,
    request: EnrollmentCreate,
) -> int | None:
    return db.scalar(
        select(StudentEnrollment.id).where(
            StudentEnrollment.user_id == user_id,
            StudentEnrollment.term_id == term_id,
            func.upper(StudentEnrollment.course_code) == request.course_code,
            func.upper(StudentEnrollment.section) == request.section,
            func.upper(StudentEnrollment.semester) == request.semester.upper(),
        )
    )


def _entry_summary(entry: TimetableEntry) -> dict:
    return {
        "id": entry.id,
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "section": entry.section,
        "semester": entry.semester,
        "faculty": entry.faculty,
        "room": entry.room,
        "day": entry.day,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
    }


def _matches_enrollment(
    entry: TimetableEntry,
    *,
    course_code: str,
    section: str,
    semester: str,
) -> bool:
    return (
        (entry.course_code or "").strip().upper() == course_code
        and section_matches(section, entry.section)
        and semester_matches(semester, entry.semester)
    )


def validate_student_enrollment(
    db: Session,
    *,
    user_id: int,
    request: EnrollmentCreate,
    reject_duplicate: bool = True,
) -> dict:
    active_term = get_active_term(db)
    if reject_duplicate and _find_existing_enrollment(
        db,
        user_id=user_id,
        term_id=active_term.id,
        request=request,
    ) is not None:
        raise HTTPException(
            status_code=409,
            detail="This course enrollment already exists.",
        )

    course_entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(
                TimetableEntry.term_id == active_term.id,
                TimetableEntry.entry_kind == "course",
                TimetableEntry.course_code.is_not(None),
                func.upper(TimetableEntry.course_code) == request.course_code,
            )
            .order_by(TimetableEntry.id)
        ).all()
    )
    proposed_entries = [
        entry
        for entry in course_entries
        if _matches_enrollment(
            entry,
            course_code=request.course_code,
            section=request.section,
            semester=request.semester,
        )
    ]
    existing_entries = get_student_timetable(db, user_id)
    conflicts: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()
    for proposed in proposed_entries:
        for existing in existing_entries:
            if proposed.id == existing.id or not times_overlap(proposed, existing):
                continue
            identity = (proposed.id, existing.id)
            if identity in seen_pairs:
                continue
            seen_pairs.add(identity)
            conflicts.append(
                {
                    "proposed_class": _entry_summary(proposed),
                    "conflicts_with": _entry_summary(existing),
                    "day": proposed.day,
                    "overlap_start": max(proposed.start_time, existing.start_time),
                    "overlap_end": min(proposed.end_time, existing.end_time),
                }
            )

    alternate_sections: list[dict] = []
    known_sections = sorted(
        {
            normalize_section(section)
            for entry in course_entries
            if semester_matches(request.semester, entry.semester) and entry.section
            for section in entry.section.split(",")
            if section.strip()
        }
        - {request.section}
    )
    alternate_limitations = [
        "Section capacity and seat availability are not modeled.",
        "Program eligibility and registration approval are not verified.",
        "The student is never moved to an alternate section automatically.",
    ]
    for section in known_sections:
        section_entries = [
            entry
            for entry in course_entries
            if _matches_enrollment(
                entry,
                course_code=request.course_code,
                section=section,
                semester=request.semester,
            )
        ]
        has_conflict = any(
            candidate.id != existing.id and times_overlap(candidate, existing)
            for candidate in section_entries
            for existing in existing_entries
        )
        alternate_sections.append(
            {
                "section": section,
                "timetable_entry_ids": [entry.id for entry in section_entries],
                "conflict_free": not has_conflict,
                "validation_status": "timetable_only_unverified",
                "limitations": alternate_limitations,
            }
        )

    limitations: list[str] = []
    if not proposed_entries:
        limitations.append(
            "No current timetable entry maps to this course, section, and semester."
        )
    if alternate_sections:
        limitations.append(
            "Alternate sections are timetable-only possibilities, not verified seat offers."
        )
    return {
        "course_code": request.course_code,
        "section": request.section,
        "semester": request.semester,
        "mapped_timetable_entry_ids": [entry.id for entry in proposed_entries],
        "has_conflicts": bool(conflicts),
        "conflicts": conflicts,
        "alternate_sections": alternate_sections,
        "limitations": limitations,
    }


def create_student_enrollment(
    db: Session,
    *,
    user_id: int,
    request: EnrollmentCreate,
) -> StudentEnrollment:
    active_term = get_active_term(db)
    existing = _find_existing_enrollment(
        db,
        user_id=user_id,
        term_id=active_term.id,
        request=request,
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This course enrollment already exists.",
        )

    conflict_validation = validate_student_enrollment(
        db,
        user_id=user_id,
        request=request,
        reject_duplicate=False,
    )
    enrollment = StudentEnrollment(
        term_id=active_term.id,
        user_id=user_id,
        course_code=request.course_code,
        section=request.section,
        semester=request.semester,
    )
    db.add(enrollment)

    try:
        db.flush()
        record_learning_event(
            db,
            term_id=enrollment.term_id,
            event_type="student_enrolled",
            subject_key=stable_learning_key("student", user_id),
            entity_type="enrollment",
            entity_key=stable_learning_key("enrollment", enrollment.id),
            actor_role="student",
            outcome_label=(
                "conflict_detected"
                if conflict_validation["has_conflicts"]
                else "no_conflict"
            ),
            context={
                "course_code": enrollment.course_code,
                "section": enrollment.section,
                "semester": enrollment.semester,
                "mapped_entry_count": len(
                    conflict_validation["mapped_timetable_entry_ids"]
                ),
                "conflict_count": len(conflict_validation["conflicts"]),
                "alternate_section_count": len(
                    conflict_validation["alternate_sections"]
                ),
            },
        )
        db.commit()
        db.refresh(enrollment)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This course enrollment already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    enrollment.conflict_validation = conflict_validation
    return enrollment


def delete_student_enrollment(
    db: Session,
    *,
    user_id: int,
    enrollment_id: int,
) -> None:
    enrollment = db.get(StudentEnrollment, enrollment_id)
    if enrollment is None or enrollment.user_id != user_id:
        raise HTTPException(status_code=404, detail="Enrollment not found.")

    require_active_term_id(db, enrollment.term_id)

    record_learning_event(
        db,
        term_id=enrollment.term_id,
        event_type="student_dropped",
        subject_key=stable_learning_key("student", user_id),
        entity_type="enrollment",
        entity_key=stable_learning_key("enrollment", enrollment.id),
        actor_role="student",
        outcome_label="dropped",
        context={
            "course_code": enrollment.course_code,
            "section": enrollment.section,
            "semester": enrollment.semester,
        },
    )
    db.delete(enrollment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

def get_student_timetable(db: Session, user_id: int):
    active_term = get_active_term(db)
    enrollments = list_student_enrollments(db, user_id, term_id=active_term.id)
    if not enrollments:
        return []

    course_codes = {enrollment.course_code.strip().upper() for enrollment in enrollments}
    statement = select(TimetableEntry).where(
        TimetableEntry.term_id == active_term.id,
        TimetableEntry.course_code.is_not(None),
        func.upper(TimetableEntry.course_code).in_(course_codes),
    )
    entries = list(db.scalars(statement).all())

    matches = []
    seen_ids = set()

    for entry in entries:
        entry_code = (entry.course_code or "").strip().upper()
        if entry_code not in course_codes:
            continue

        for enrollment in enrollments:
            if enrollment.course_code.strip().upper() != entry_code:
                continue
            if not section_matches(enrollment.section, entry.section):
                continue
            if not semester_matches(enrollment.semester, entry.semester):
                continue

            if entry.id not in seen_ids:
                matches.append(entry)
                seen_ids.add(entry.id)
            break

    return sorted(matches, key=timetable_sort_key)
