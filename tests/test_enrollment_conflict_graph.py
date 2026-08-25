from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.database import Base
from backend.enrollment_conflict_graph import (
    build_enrollment_conflict_analysis,
    summarize_enrollment_conflicts,
)
from backend.models import StudentEnrollment, StudentProfile, TimetableEntry, User
from backend.student_conflict_groups import (
    build_student_conflict_groups,
    summarize_student_conflict_groups,
)


def create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_student(
    db,
    registration_number: str,
    *,
    is_verified: bool = True,
    is_active: bool = True,
) -> User:
    user = User(
        email=f"{registration_number.lower()}@example.edu",
        full_name=registration_number,
        password_hash=hash_password("Password123"),
        role="student",
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    db.add(
        StudentProfile(
            user_id=user.id,
            registration_number=registration_number,
            department="Computing",
            program="BS AI",
            batch="2026",
            current_semester=3,
            section="A",
            is_verified=is_verified,
            onboarding_completed=True,
        )
    )
    db.flush()
    return user


def add_enrollment(db, user: User, course_code: str, section: str) -> None:
    db.add(
        StudentEnrollment(
            user_id=user.id,
            course_code=course_code,
            section=section,
            semester="Fall 2026",
        )
    )


def overlapping_entries(db) -> tuple[TimetableEntry, TimetableEntry]:
    first = TimetableEntry(
        course_code="AI-232",
        course_name="Artificial Intelligence",
        semester="Fall 2026",
        section="A",
        day="Tuesday",
        start_time="10:00",
        end_time="11:30",
    )
    second = TimetableEntry(
        course_code="CS-242",
        course_name="Algorithms",
        semester="Fall 2026",
        section="B",
        day="Tuesday",
        start_time="10:30",
        end_time="12:00",
    )
    db.add_all([first, second])
    db.flush()
    return first, second


def test_real_enrollment_edge_confirms_weight_even_when_sections_differ():
    Session = create_session()
    with Session() as db:
        first, second = overlapping_entries(db)
        for number in ("FA23-001", "FA23-002"):
            student = create_student(db, number)
            add_enrollment(db, student, "AI-232", "A")
            add_enrollment(db, student, "CS-242", "B")
        only_first = create_student(db, "FA23-003")
        add_enrollment(db, only_first, "AI-232", "A")
        unverified = create_student(db, "FA23-004", is_verified=False)
        add_enrollment(db, unverified, "AI-232", "A")
        add_enrollment(db, unverified, "CS-242", "B")
        inactive = create_student(db, "FA23-005", is_active=False)
        add_enrollment(db, inactive, "AI-232", "A")
        add_enrollment(db, inactive, "CS-242", "B")
        db.commit()

        analysis = build_enrollment_conflict_analysis(db, [first, second])
        assert len(analysis["risks"]) == 1
        risk = analysis["risks"][0]
        assert risk["risk_level"] == "confirmed"
        assert risk["evidence_source"] == "enrollment"
        assert risk["affected_student_count"] == 2
        assert risk["shared_sections"] == []
        assert analysis["coverage"]["enrollment_backed_edges"] == 1
        assert analysis["coverage"]["verified_students"] == 3

        groups = build_student_conflict_groups(analysis["risks"])
        assert len(groups) == 1
        assert groups[0]["enrollment_backed_edges"] == 1
        assert groups[0]["evidence_sources"] == ["enrollment"]
        assert summarize_student_conflict_groups(groups)["enrollment_backed_groups"] == 1


def test_timetable_only_signal_is_never_presented_as_confirmed():
    Session = create_session()
    with Session() as db:
        first = TimetableEntry(
            course_code="AI-232",
            semester="Fall 2026",
            section="A",
            day="Monday",
            start_time="09:00",
            end_time="10:00",
        )
        second = TimetableEntry(
            course_code="CS-242",
            semester="Fall 2026",
            section="A",
            day="Monday",
            start_time="09:30",
            end_time="10:30",
        )
        db.add_all([first, second])
        db.commit()

        analysis = build_enrollment_conflict_analysis(db, [first, second])
        assert len(analysis["risks"]) == 1
        risk = analysis["risks"][0]
        assert risk["risk_level"] == "probable"
        assert risk["evidence_source"] == "timetable_inference"
        assert risk["affected_student_count"] == 0
        assert risk["enrollment_coverage"] == "none"
        summary = summarize_enrollment_conflicts(analysis)
        assert summary["confirmed"] == 0
        assert summary["inferred"] == 1


def test_complete_enrollment_coverage_suppresses_disproven_heuristic_pair():
    Session = create_session()
    with Session() as db:
        first = TimetableEntry(
            course_code="AI-232",
            semester="Fall 2026",
            section="A",
            day="Monday",
            start_time="09:00",
            end_time="10:00",
        )
        second = TimetableEntry(
            course_code="CS-242",
            semester="Fall 2026",
            section="A",
            day="Monday",
            start_time="09:30",
            end_time="10:30",
        )
        db.add_all([first, second])
        first_student = create_student(db, "FA23-010")
        second_student = create_student(db, "FA23-011")
        add_enrollment(db, first_student, "AI-232", "A")
        add_enrollment(db, second_student, "CS-242", "A")
        db.commit()

        analysis = build_enrollment_conflict_analysis(db, [first, second])
        assert analysis["risks"] == []
        assert analysis["coverage"]["entries_with_enrollment_data"] == 2


def test_missing_course_offering_is_counted_as_unmapped_data_quality_issue():
    Session = create_session()
    with Session() as db:
        student = create_student(db, "FA23-020")
        add_enrollment(db, student, "MISSING-999", "A")
        db.commit()

        analysis = build_enrollment_conflict_analysis(db, [])
        assert analysis["coverage"]["enrollment_records"] == 1
        assert analysis["coverage"]["mapped_enrollment_records"] == 0
        assert analysis["coverage"]["unmapped_enrollment_records"] == 1
        assert len(analysis["coverage"]["unmapped_enrollment_ids"]) == 1
        assert summarize_enrollment_conflicts(analysis)["unmapped_enrollment_records"] == 1

