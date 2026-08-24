from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.faculty_schemas import FacultyAssignmentCreate
from backend.models import FacultyClassAssignment, TimetableEntry, User
from backend.schedule_matching import (
    section_matches,
    semester_matches,
    timetable_sort_key,
)


def list_faculty_directory(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    filters = [
        User.role == "faculty",
        User.is_active.is_(True),
    ]
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    faculty = list(
        db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.full_name, User.id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {
        "faculty": faculty,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _serialize_assignment(
    db: Session,
    assignment: FacultyClassAssignment,
) -> dict:
    faculty = db.get(User, assignment.faculty_user_id)
    if faculty is None:
        raise HTTPException(status_code=500, detail="Assigned faculty user could not be loaded.")
    return {
        "id": assignment.id,
        "faculty_user_id": assignment.faculty_user_id,
        "faculty_name": faculty.full_name,
        "faculty_email": faculty.email,
        "course_code": assignment.course_code,
        "section": assignment.section,
        "semester": assignment.semester,
        "created_by_user_id": assignment.created_by_user_id,
        "created_at": assignment.created_at,
    }


def list_faculty_assignments(
    db: Session,
    *,
    faculty_user_id: int | None = None,
) -> list[dict]:
    statement = select(FacultyClassAssignment)
    if faculty_user_id is not None:
        statement = statement.where(
            FacultyClassAssignment.faculty_user_id == faculty_user_id
        )
    statement = statement.order_by(
        FacultyClassAssignment.semester,
        FacultyClassAssignment.course_code,
        FacultyClassAssignment.section,
        FacultyClassAssignment.id,
    )
    assignments = list(db.scalars(statement).all())
    return [_serialize_assignment(db, assignment) for assignment in assignments]


def create_faculty_assignment(
    db: Session,
    *,
    created_by_user_id: int,
    request: FacultyAssignmentCreate,
) -> dict:
    faculty = db.get(User, request.faculty_user_id)
    if faculty is None or faculty.role != "faculty" or not faculty.is_active:
        raise HTTPException(
            status_code=422,
            detail="faculty_user_id must reference an active faculty account.",
        )

    existing = db.scalar(
        select(FacultyClassAssignment.id).where(
            FacultyClassAssignment.faculty_user_id == faculty.id,
            func.upper(FacultyClassAssignment.course_code) == request.course_code,
            func.upper(FacultyClassAssignment.section) == request.section,
            func.upper(FacultyClassAssignment.semester) == request.semester.upper(),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This faculty class assignment already exists.",
        )

    assignment = FacultyClassAssignment(
        faculty_user_id=faculty.id,
        course_code=request.course_code,
        section=request.section,
        semester=request.semester,
        created_by_user_id=created_by_user_id,
    )
    db.add(assignment)
    try:
        db.commit()
        db.refresh(assignment)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This faculty class assignment already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    return _serialize_assignment(db, assignment)


def delete_faculty_assignment(db: Session, assignment_id: int) -> None:
    assignment = db.get(FacultyClassAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Faculty assignment not found.")
    db.delete(assignment)
    db.commit()


def get_faculty_timetable(db: Session, faculty_user_id: int) -> list[TimetableEntry]:
    assignments = list(
        db.scalars(
            select(FacultyClassAssignment).where(
                FacultyClassAssignment.faculty_user_id == faculty_user_id
            )
        ).all()
    )
    if not assignments:
        return []

    course_codes = {
        assignment.course_code.strip().upper() for assignment in assignments
    }
    entries = list(
        db.scalars(
            select(TimetableEntry).where(
                TimetableEntry.course_code.is_not(None),
                func.upper(TimetableEntry.course_code).in_(course_codes),
            )
        ).all()
    )
    matches = []
    seen_ids = set()
    for entry in entries:
        entry_code = (entry.course_code or "").strip().upper()
        if entry_code not in course_codes:
            continue
        for assignment in assignments:
            if assignment.course_code.strip().upper() != entry_code:
                continue
            if not section_matches(assignment.section, entry.section):
                continue
            if not semester_matches(assignment.semester, entry.semester):
                continue
            if entry.id not in seen_ids:
                matches.append(entry)
                seen_ids.add(entry.id)
            break
    return sorted(matches, key=timetable_sort_key)
