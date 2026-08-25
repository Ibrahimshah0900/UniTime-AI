from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.enrollment_schemas import EnrollmentCreate
from backend.models import StudentEnrollment
from backend.schedule_matching import (
    section_matches,
    semester_matches,
    timetable_sort_key,
)
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


def create_student_enrollment(
    db: Session,
    *,
    user_id: int,
    request: EnrollmentCreate,
) -> StudentEnrollment:
    active_term = get_active_term(db)
    existing = db.scalar(
        select(StudentEnrollment.id).where(
            StudentEnrollment.user_id == user_id,
            StudentEnrollment.term_id == active_term.id,
            func.upper(StudentEnrollment.course_code) == request.course_code,
            func.upper(StudentEnrollment.section) == request.section,
            func.upper(StudentEnrollment.semester) == request.semester.upper(),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This course enrollment already exists.",
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

    db.delete(enrollment)
    db.commit()

def get_student_timetable(db: Session, user_id: int):
    active_term = get_active_term(db)
    enrollments = list_student_enrollments(db, user_id, term_id=active_term.id)
    if not enrollments:
        return []

    from backend.models import TimetableEntry

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
