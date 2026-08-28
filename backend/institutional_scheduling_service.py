from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.institutional_scheduling_schemas import (
    CourseOfferingCreate,
    CourseOfferingUpdate,
    FacultyAvailabilityCreate,
)
from backend.models import (
    AcademicTerm,
    CourseOffering,
    FacultyAvailabilityWindow,
    FacultyClassAssignment,
    FacultyTeachingProfile,
    User,
)
from backend.schedule_matching import normalize_course_code, normalize_section
from backend.scheduling_policy import DEFAULT_SCHEDULING_POLICY, time_to_minutes
from backend.term_service import get_active_term, get_term


DESIGNATION_SUBJECT_LIMITS = {
    "lecturer": 4,
    "assistant_professor": 2,
}


def _read_term(db: Session, term_id: int | None) -> AcademicTerm:
    return get_active_term(db) if term_id is None else get_term(db, term_id)


def _planning_term(db: Session, term_id: int) -> AcademicTerm:
    term = get_term(db, term_id)
    if term.status != "planning":
        raise HTTPException(
            status_code=409,
            detail="Institutional scheduling preparation is only writable in a planning academic term.",
        )
    return term


def _active_faculty(db: Session, faculty_user_id: int) -> User:
    faculty = db.get(User, faculty_user_id)
    if faculty is None or faculty.role != "faculty" or not faculty.is_active:
        raise HTTPException(
            status_code=422,
            detail="faculty_user_id must reference an active faculty account.",
        )
    if not faculty.email:
        raise HTTPException(
            status_code=409,
            detail="Faculty account requires an institutional email before scheduling.",
        )
    return faculty


def list_course_offerings(
    db: Session,
    *,
    term_id: int | None = None,
) -> list[CourseOffering]:
    term = _read_term(db, term_id)
    return list(
        db.scalars(
            select(CourseOffering)
            .where(CourseOffering.term_id == term.id)
            .order_by(
                CourseOffering.semester,
                CourseOffering.course_code,
                CourseOffering.section,
                CourseOffering.class_type,
                CourseOffering.id,
            )
        ).all()
    )


def _duplicate_offering(
    db: Session,
    *,
    term_id: int,
    course_code: str,
    semester: int,
    section: str,
    class_type: str,
    exclude_id: int | None = None,
) -> CourseOffering | None:
    statement = select(CourseOffering).where(
        CourseOffering.term_id == term_id,
        func.upper(CourseOffering.course_code) == course_code.upper(),
        CourseOffering.semester == semester,
        func.upper(CourseOffering.section) == section.upper(),
        CourseOffering.class_type == class_type,
    )
    if exclude_id is not None:
        statement = statement.where(CourseOffering.id != exclude_id)
    return db.scalar(statement)


def create_course_offering(
    db: Session,
    *,
    actor_user_id: int,
    request: CourseOfferingCreate,
) -> CourseOffering:
    _planning_term(db, request.term_id)
    if _duplicate_offering(
        db,
        term_id=request.term_id,
        course_code=request.course_code,
        semester=request.semester,
        section=request.section,
        class_type=request.class_type,
    ):
        raise HTTPException(status_code=409, detail="This course offering already exists.")

    offering = CourseOffering(
        **request.model_dump(),
        created_by_user_id=actor_user_id,
    )
    db.add(offering)
    try:
        db.commit()
        db.refresh(offering)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This course offering already exists.") from exc
    except Exception:
        db.rollback()
        raise
    return offering


def update_course_offering(
    db: Session,
    *,
    offering_id: int,
    request: CourseOfferingUpdate,
) -> CourseOffering:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="Course offering not found.")
    _planning_term(db, offering.term_id)

    changes = request.model_dump(exclude_unset=True)
    if not changes:
        return offering

    next_values = {
        "course_code": changes.get("course_code", offering.course_code),
        "semester": changes.get("semester", offering.semester),
        "section": changes.get("section", offering.section),
        "class_type": changes.get("class_type", offering.class_type),
    }
    duplicate = _duplicate_offering(
        db,
        term_id=offering.term_id,
        course_code=next_values["course_code"],
        semester=next_values["semester"],
        section=next_values["section"],
        class_type=next_values["class_type"],
        exclude_id=offering.id,
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This course offering already exists.")

    if any(
        key in changes
        for key in ("course_code", "semester", "section")
    ):
        assignment = db.scalar(
            select(FacultyClassAssignment.id).where(
                FacultyClassAssignment.term_id == offering.term_id,
                func.upper(FacultyClassAssignment.course_code) == offering.course_code.upper(),
                func.upper(FacultyClassAssignment.section) == offering.section.upper(),
                func.upper(FacultyClassAssignment.semester) == str(offering.semester).upper(),
            )
        )
        if assignment is not None:
            raise HTTPException(
                status_code=409,
                detail="Remove the faculty allocation before changing this offering identity.",
            )

    for field, value in changes.items():
        setattr(offering, field, value)
    try:
        db.commit()
        db.refresh(offering)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This course offering already exists.") from exc
    except Exception:
        db.rollback()
        raise
    return offering


def delete_course_offering(db: Session, *, offering_id: int) -> None:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="Course offering not found.")
    _planning_term(db, offering.term_id)
    assignment = db.scalar(
        select(FacultyClassAssignment.id).where(
            FacultyClassAssignment.term_id == offering.term_id,
            func.upper(FacultyClassAssignment.course_code) == offering.course_code.upper(),
            func.upper(FacultyClassAssignment.section) == offering.section.upper(),
            func.upper(FacultyClassAssignment.semester) == str(offering.semester).upper(),
        )
    )
    if assignment is not None:
        raise HTTPException(
            status_code=409,
            detail="Remove the faculty allocation before deleting this course offering.",
        )
    db.delete(offering)
    db.commit()


def set_faculty_designation(
    db: Session,
    *,
    faculty_user_id: int,
    designation: str,
) -> dict:
    faculty = _active_faculty(db, faculty_user_id)
    maximum = DESIGNATION_SUBJECT_LIMITS[designation]
    assignments = list(
        db.scalars(
            select(FacultyClassAssignment).where(
                FacultyClassAssignment.faculty_user_id == faculty.id
            )
        ).all()
    )
    subjects_by_term: dict[int, set[str]] = {}
    for assignment in assignments:
        code = normalize_course_code(assignment.course_code)
        if code:
            subjects_by_term.setdefault(assignment.term_id, set()).add(code)
    overloaded_terms = sorted(
        term_id
        for term_id, codes in subjects_by_term.items()
        if len(codes) > maximum
    )
    if overloaded_terms:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot set designation because existing teaching load exceeds the "
                f"{maximum}-subject limit in term(s): "
                + ", ".join(str(term_id) for term_id in overloaded_terms)
                + "."
            ),
        )

    profile = db.get(FacultyTeachingProfile, faculty.id)
    if profile is None:
        profile = FacultyTeachingProfile(
            user_id=faculty.id,
            designation=designation,
        )
        db.add(profile)
    else:
        profile.designation = designation
    db.commit()
    db.refresh(profile)
    return {
        "faculty_user_id": faculty.id,
        "faculty_name": faculty.full_name,
        "faculty_email": faculty.email,
        "designation": profile.designation,
        "profile_configured": True,
    }


def _distinct_subject_codes(
    db: Session,
    *,
    faculty_user_id: int,
    term_id: int,
) -> list[str]:
    rows = db.scalars(
        select(FacultyClassAssignment.course_code)
        .where(
            FacultyClassAssignment.faculty_user_id == faculty_user_id,
            FacultyClassAssignment.term_id == term_id,
        )
        .order_by(FacultyClassAssignment.course_code)
    ).all()
    return sorted({normalize_course_code(code) for code in rows if normalize_course_code(code)})


def get_faculty_workload(
    db: Session,
    *,
    faculty_user_id: int,
    term_id: int | None = None,
) -> dict:
    faculty = _active_faculty(db, faculty_user_id)
    term = _read_term(db, term_id)
    profile = db.get(FacultyTeachingProfile, faculty.id)
    designation = profile.designation if profile is not None else None
    maximum = DESIGNATION_SUBJECT_LIMITS.get(designation) if designation else None
    subject_codes = _distinct_subject_codes(
        db,
        faculty_user_id=faculty.id,
        term_id=term.id,
    )
    remaining = None if maximum is None else max(maximum - len(subject_codes), 0)
    return {
        "faculty_user_id": faculty.id,
        "faculty_name": faculty.full_name,
        "faculty_email": faculty.email,
        "designation": designation,
        "profile_configured": profile is not None,
        "term_id": term.id,
        "distinct_subjects_assigned": len(subject_codes),
        "maximum_subjects": maximum,
        "remaining_capacity": remaining,
        "subject_codes": subject_codes,
    }


def list_faculty_workloads(
    db: Session,
    *,
    term_id: int | None = None,
    faculty_user_id: int | None = None,
) -> list[dict]:
    term = _read_term(db, term_id)
    if faculty_user_id is not None:
        return [
            get_faculty_workload(
                db,
                faculty_user_id=faculty_user_id,
                term_id=term.id,
            )
        ]
    faculty_ids = list(
        db.scalars(
            select(User.id)
            .where(User.role == "faculty", User.is_active.is_(True))
            .order_by(User.full_name, User.id)
        ).all()
    )
    return [
        get_faculty_workload(db, faculty_user_id=user_id, term_id=term.id)
        for user_id in faculty_ids
    ]


def validate_faculty_assignment_request(
    db: Session,
    *,
    faculty: User,
    term: AcademicTerm,
    course_code: str,
    section: str,
    semester: str,
) -> None:
    normalized_course = normalize_course_code(course_code)
    normalized_section = normalize_section(section)
    if not normalized_course or not normalized_section:
        raise HTTPException(status_code=422, detail="Course code and section are required.")

    profile = db.get(FacultyTeachingProfile, faculty.id)

    if term.status == "planning":
        if profile is None:
            raise HTTPException(
                status_code=409,
                detail="Set the faculty teaching designation before allocating planning-term subjects.",
            )
        try:
            semester_number = int(str(semester).strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Planning-term faculty allocations must use semester numbers 1 through 8.",
            ) from exc
        offering = db.scalar(
            select(CourseOffering.id).where(
                CourseOffering.term_id == term.id,
                func.upper(CourseOffering.course_code) == normalized_course.upper(),
                CourseOffering.semester == semester_number,
                func.upper(CourseOffering.section) == normalized_section.upper(),
            )
        )
        if offering is None:
            raise HTTPException(
                status_code=409,
                detail="Create the matching planning-term course offering before allocating faculty.",
            )

        existing_owner_ids = set(
            db.scalars(
                select(FacultyClassAssignment.faculty_user_id).where(
                    FacultyClassAssignment.term_id == term.id,
                    func.upper(FacultyClassAssignment.course_code)
                    == normalized_course.upper(),
                    func.upper(FacultyClassAssignment.section)
                    == normalized_section.upper(),
                    func.upper(FacultyClassAssignment.semester)
                    == str(semester_number).upper(),
                )
            ).all()
        )
        if existing_owner_ids and existing_owner_ids != {faculty.id}:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This planning-term offered subject is already allocated "
                    "to another faculty member."
                ),
            )

    designation = profile.designation if profile is not None else "lecturer"
    maximum = DESIGNATION_SUBJECT_LIMITS[designation]
    existing_subjects = _distinct_subject_codes(
        db,
        faculty_user_id=faculty.id,
        term_id=term.id,
    )
    if normalized_course not in existing_subjects and len(existing_subjects) >= maximum:
        label = "Assistant Professor" if designation == "assistant_professor" else "Lecturer"
        raise HTTPException(
            status_code=409,
            detail=f"{label} teaching load is limited to {maximum} distinct subjects per academic term.",
        )


def _validate_availability_times(day: str, start_time: str, end_time: str) -> None:
    policy = DEFAULT_SCHEDULING_POLICY
    if day not in policy.operating_days:
        raise HTTPException(status_code=422, detail="Availability day is outside institutional operating days.")
    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)
    if start >= end:
        raise HTTPException(status_code=422, detail="Availability end_time must be after start_time.")
    if start < time_to_minutes(policy.opens_at) or end > time_to_minutes(policy.closes_at):
        raise HTTPException(
            status_code=422,
            detail=f"Availability must fall within institutional operating hours {policy.opens_at}-{policy.closes_at}.",
        )


def list_faculty_availability(
    db: Session,
    *,
    faculty_user_id: int,
    term_id: int | None = None,
) -> list[FacultyAvailabilityWindow]:
    _active_faculty(db, faculty_user_id)
    term = _read_term(db, term_id)
    return list(
        db.scalars(
            select(FacultyAvailabilityWindow)
            .where(
                FacultyAvailabilityWindow.faculty_user_id == faculty_user_id,
                FacultyAvailabilityWindow.term_id == term.id,
            )
            .order_by(
                FacultyAvailabilityWindow.day,
                FacultyAvailabilityWindow.start_time,
                FacultyAvailabilityWindow.end_time,
                FacultyAvailabilityWindow.id,
            )
        ).all()
    )


def create_faculty_availability(
    db: Session,
    *,
    faculty_user_id: int,
    request: FacultyAvailabilityCreate,
) -> FacultyAvailabilityWindow:
    _active_faculty(db, faculty_user_id)
    _planning_term(db, request.term_id)
    _validate_availability_times(request.day, request.start_time, request.end_time)

    overlap = db.scalar(
        select(FacultyAvailabilityWindow.id).where(
            FacultyAvailabilityWindow.term_id == request.term_id,
            FacultyAvailabilityWindow.faculty_user_id == faculty_user_id,
            FacultyAvailabilityWindow.day == request.day,
            FacultyAvailabilityWindow.start_time < request.end_time,
            FacultyAvailabilityWindow.end_time > request.start_time,
        )
    )
    if overlap is not None:
        raise HTTPException(
            status_code=409,
            detail="Faculty availability windows on the same day may not overlap.",
        )

    window = FacultyAvailabilityWindow(
        term_id=request.term_id,
        faculty_user_id=faculty_user_id,
        day=request.day,
        start_time=request.start_time,
        end_time=request.end_time,
    )
    db.add(window)
    try:
        db.commit()
        db.refresh(window)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This faculty availability window already exists.") from exc
    except Exception:
        db.rollback()
        raise
    return window


def delete_faculty_availability(
    db: Session,
    *,
    window_id: int,
    faculty_user_id: int | None = None,
) -> None:
    window = db.get(FacultyAvailabilityWindow, window_id)
    if window is None or (
        faculty_user_id is not None and window.faculty_user_id != faculty_user_id
    ):
        raise HTTPException(status_code=404, detail="Faculty availability window not found.")
    _planning_term(db, window.term_id)
    db.delete(window)
    db.commit()
