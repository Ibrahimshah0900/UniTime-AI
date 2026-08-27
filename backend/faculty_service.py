from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth_security import hash_password
from backend.faculty_schemas import FacultyAssignmentCreate, FacultyProvisionCreate
from backend.models import FacultyClassAssignment, TimetableEntry, User
from backend.schedule_matching import (
    section_matches,
    semester_matches,
    timetable_sort_key,
)
from backend.scheduling_policy import (
    DEFAULT_SCHEDULING_POLICY,
    SchedulingPolicy,
    minutes_to_time,
    time_to_minutes,
)
from backend.term_service import get_active_term, resolve_term_for_write
from backend.student_identity_service import generate_temporary_password


def provision_faculty_account(db: Session, request: FacultyProvisionCreate) -> dict:
    if db.scalar(select(User.id).where(User.email == request.email)) is not None:
        raise HTTPException(
            status_code=409,
            detail="An account with this institutional email already exists.",
        )
    temporary_password = request.temporary_password or generate_temporary_password()
    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(temporary_password),
        role="faculty",
        is_active=request.is_active,
        must_change_password=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this institutional email already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    return {"faculty": user, "temporary_password": temporary_password}


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
        "term_id": assignment.term_id,
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
    term_id: int | None = None,
) -> list[dict]:
    selected_term_id = term_id or get_active_term(db).id
    statement = select(FacultyClassAssignment).where(
        FacultyClassAssignment.term_id == selected_term_id
    )
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
    term = resolve_term_for_write(db, request.term_id, allow_planning=True)
    faculty = db.get(User, request.faculty_user_id)
    if faculty is None or faculty.role != "faculty" or not faculty.is_active:
        raise HTTPException(
            status_code=422,
            detail="faculty_user_id must reference an active faculty account.",
        )

    existing = db.scalar(
        select(FacultyClassAssignment.id).where(
            FacultyClassAssignment.faculty_user_id == faculty.id,
            FacultyClassAssignment.term_id == term.id,
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
        term_id=term.id,
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
    resolve_term_for_write(db, assignment.term_id, allow_planning=True)
    db.delete(assignment)
    db.commit()


def get_faculty_timetable(
    db: Session,
    faculty_user_id: int,
    *,
    term_id: int | None = None,
) -> list[TimetableEntry]:
    selected_term_id = term_id or get_active_term(db).id
    assignments = list(
        db.scalars(
            select(FacultyClassAssignment).where(
                FacultyClassAssignment.faculty_user_id == faculty_user_id,
                FacultyClassAssignment.term_id == selected_term_id,
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
                TimetableEntry.term_id == selected_term_id,
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

def get_faculty_free_slots(
    db: Session,
    faculty_user_id: int,
    *,
    term_id: int | None = None,
    minimum_minutes: int = 30,
    policy: SchedulingPolicy = DEFAULT_SCHEDULING_POLICY,
) -> dict:
    selected_term_id = term_id or get_active_term(db).id
    timetable = get_faculty_timetable(
        db,
        faculty_user_id,
        term_id=selected_term_id,
    )

    opening = time_to_minutes(policy.opens_at)
    closing = time_to_minutes(policy.closes_at)
    busy_by_day: dict[str, list[tuple[int, int]]] = {
        day: [] for day in policy.operating_days
    }

    for period in policy.blocked_periods:
        busy_by_day[period.day].append(
            (
                max(opening, time_to_minutes(period.start_time)),
                min(closing, time_to_minutes(period.end_time)),
            )
        )

    for entry in timetable:
        if entry.day not in busy_by_day:
            continue
        start = max(opening, time_to_minutes(entry.start_time))
        end = min(closing, time_to_minutes(entry.end_time))
        if start < end:
            busy_by_day[entry.day].append((start, end))

    slots: list[dict] = []
    for day in policy.operating_days:
        intervals = sorted(busy_by_day[day])
        merged: list[list[int]] = []

        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        cursor = opening
        for start, end in merged:
            if start - cursor >= minimum_minutes:
                slots.append(
                    {
                        "day": day,
                        "start_time": minutes_to_time(cursor),
                        "end_time": minutes_to_time(start),
                        "duration_minutes": start - cursor,
                    }
                )
            cursor = max(cursor, end)

        if closing - cursor >= minimum_minutes:
            slots.append(
                {
                    "day": day,
                    "start_time": minutes_to_time(cursor),
                    "end_time": minutes_to_time(closing),
                    "duration_minutes": closing - cursor,
                }
            )

    return {
        "term_id": selected_term_id,
        "opens_at": policy.opens_at,
        "closes_at": policy.closes_at,
        "minimum_minutes": minimum_minutes,
        "slots": slots,
        "note": (
            "These are gaps in your assigned timetable within institutional "
            "operating hours; they do not confirm personal faculty availability."
        ),
    }
