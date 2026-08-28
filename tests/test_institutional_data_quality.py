from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.data_quality_service import run_data_quality_report
from backend.database import Base
from backend.models import (
    AcademicTerm,
    CourseOffering,
    FacultyAvailabilityWindow,
    FacultyClassAssignment,
    FacultyTeachingProfile,
    TimetableEntry,
    User,
)


def create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def add_user(
    db,
    *,
    email: str,
    role: str = "faculty",
    active: bool = True,
    full_name: str | None = None,
) -> User:
    user = User(
        email=email,
        full_name=full_name or email.split("@")[0],
        password_hash=hash_password("Password123"),
        role=role,
        is_active=active,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def add_offering(
    db,
    *,
    term_id: int,
    code: str,
    semester: int,
    room: str | None = "R-101",
) -> CourseOffering:
    offering = CourseOffering(
        term_id=term_id,
        course_code=code,
        course_name=f"{code} Course",
        semester=semester,
        section="A",
        class_type="lecture",
        duration_minutes=60,
        room=room,
    )
    db.add(offering)
    db.flush()
    return offering


def add_assignment(
    db,
    *,
    term_id: int,
    faculty_id: int,
    code: str,
    semester: int,
) -> FacultyClassAssignment:
    assignment = FacultyClassAssignment(
        term_id=term_id,
        faculty_user_id=faculty_id,
        course_code=code,
        section="A",
        semester=str(semester),
    )
    db.add(assignment)
    db.flush()
    return assignment


def test_scheduling_data_quality_surfaces_generation_readiness_problems():
    Session = create_session()
    with Session() as db:
        term = AcademicTerm(
            code="PLAN-2027",
            name="Planning 2027",
            status="planning",
        )
        db.add(term)
        db.flush()

        add_offering(
            db,
            term_id=term.id,
            code="CS-101",
            semester=1,
            room=None,
        )

        faculty = add_user(
            db,
            email="faculty@example.edu",
            full_name="Faculty One",
        )
        no_profile = add_offering(
            db,
            term_id=term.id,
            code="CS-201",
            semester=2,
        )
        add_assignment(
            db,
            term_id=term.id,
            faculty_id=faculty.id,
            code=no_profile.course_code,
            semester=no_profile.semester,
        )

        db.commit()
        report = run_data_quality_report(
            db,
            term_id=term.id,
        )
        codes = {
            issue["issue_code"]
            for issue in report["issues"]
        }

        assert "OFFERING_WITHOUT_FACULTY_ALLOCATION" in codes
        assert "OFFERING_MISSING_ROOM" in codes
        assert "MISSING_FACULTY_TEACHING_PROFILE" in codes
        assert "FACULTY_MISSING_AVAILABILITY" in codes


def test_scheduling_data_quality_detects_overload_ambiguous_allocation_and_required_day_gap():
    Session = create_session()
    with Session() as db:
        term = AcademicTerm(
            code="PLAN-OVERLOAD",
            name="Planning Overload",
            status="planning",
        )
        db.add(term)
        db.flush()

        lecturer = add_user(
            db,
            email="lecturer@example.edu",
            full_name="Lecturer One",
        )
        second_faculty = add_user(
            db,
            email="second@example.edu",
            full_name="Second Lecturer",
        )
        db.add_all(
            [
                FacultyTeachingProfile(
                    user_id=lecturer.id,
                    designation="lecturer",
                ),
                FacultyTeachingProfile(
                    user_id=second_faculty.id,
                    designation="lecturer",
                ),
            ]
        )

        for index in range(1, 6):
            code = f"CS-{300 + index}"
            add_offering(
                db,
                term_id=term.id,
                code=code,
                semester=3,
                room=f"R-{index}",
            )
            add_assignment(
                db,
                term_id=term.id,
                faculty_id=lecturer.id,
                code=code,
                semester=3,
            )

        add_assignment(
            db,
            term_id=term.id,
            faculty_id=second_faculty.id,
            code="CS-301",
            semester=3,
        )

        db.add(
            FacultyAvailabilityWindow(
                term_id=term.id,
                faculty_user_id=lecturer.id,
                day="Monday",
                start_time="08:00",
                end_time="12:00",
            )
        )
        db.add(
            FacultyAvailabilityWindow(
                term_id=term.id,
                faculty_user_id=second_faculty.id,
                day="Monday",
                start_time="08:00",
                end_time="12:00",
            )
        )

        db.commit()
        report = run_data_quality_report(
            db,
            term_id=term.id,
        )
        codes = {
            issue["issue_code"]
            for issue in report["issues"]
        }

        assert "FACULTY_LOAD_EXCEEDS_DESIGNATION_LIMIT" in codes
        assert "AMBIGUOUS_OFFERING_FACULTY_ALLOCATION" in codes
        assert "FACULTY_REQUIRED_DAY_AVAILABILITY_MISSING" in codes


def test_generated_timetable_metadata_mismatch_is_reported_without_inventing_capacity_data():
    Session = create_session()
    with Session() as db:
        term = AcademicTerm(
            code="PLAN-GENERATED",
            name="Planning Generated",
            status="planning",
        )
        db.add(term)
        db.flush()

        faculty = add_user(
            db,
            email="generated@example.edu",
            full_name="Generated Faculty",
        )
        db.add(
            FacultyTeachingProfile(
                user_id=faculty.id,
                designation="lecturer",
            )
        )
        offering = add_offering(
            db,
            term_id=term.id,
            code="AI-401",
            semester=4,
            room="R-401",
        )
        add_assignment(
            db,
            term_id=term.id,
            faculty_id=faculty.id,
            code=offering.course_code,
            semester=offering.semester,
        )
        for day in ("Tuesday", "Thursday"):
            db.add(
                FacultyAvailabilityWindow(
                    term_id=term.id,
                    faculty_user_id=faculty.id,
                    day=day,
                    start_time="08:00",
                    end_time="12:00",
                )
            )

        db.add(
            TimetableEntry(
                term_id=term.id,
                entry_kind="course",
                course_code=offering.course_code,
                course_name=offering.course_name,
                semester="4",
                section="A",
                faculty=faculty.full_name,
                room="WRONG-ROOM",
                day="Monday",
                start_time="08:00",
                end_time="09:00",
                class_type="lecture",
                source="generated",
            )
        )

        db.commit()
        report = run_data_quality_report(
            db,
            term_id=term.id,
        )
        codes = {
            issue["issue_code"]
            for issue in report["issues"]
        }

        assert "GENERATED_ENTRY_POLICY_MISMATCH" in codes
        assert "GENERATED_ENTRY_OFFERING_METADATA_MISMATCH" in codes
        assert all(
            "CAPACITY" not in issue["issue_code"]
            for issue in report["issues"]
        )
