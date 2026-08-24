from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.enrollment_schemas import EnrollmentCreate
from backend.models import StudentEnrollment


def list_student_enrollments(db: Session, user_id: int) -> list[StudentEnrollment]:
    statement = (
        select(StudentEnrollment)
        .where(StudentEnrollment.user_id == user_id)
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
    enrollment = StudentEnrollment(
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

    db.delete(enrollment)
    db.commit()

def _section_matches(enrolled_section: str, timetable_section: str | None) -> bool:
    if timetable_section is None or not timetable_section.strip():
        return True
    sections = {part.strip().upper() for part in timetable_section.split(",") if part.strip()}
    return enrolled_section.strip().upper() in sections


def get_student_timetable(db: Session, user_id: int):
    enrollments = list_student_enrollments(db, user_id)
    if not enrollments:
        return []

    from backend.models import TimetableEntry

    course_codes = {enrollment.course_code.strip().upper() for enrollment in enrollments}
    statement = select(TimetableEntry).where(TimetableEntry.course_code.is_not(None))
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
            if not _section_matches(enrollment.section, entry.section):
                continue
            if entry.semester and enrollment.semester.strip().lower() != entry.semester.strip().lower():
                continue

            if entry.id not in seen_ids:
                matches.append(entry)
                seen_ids.add(entry.id)
            break

    return sorted(matches, key=lambda item: (item.day, item.start_time, item.course_code or ""))
