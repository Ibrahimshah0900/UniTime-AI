from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.clash_detector import detect_clashes
from backend.clash_report_schemas import (
    ClashReportCreate,
    ClashReportResolutionApplyRequest,
    ClashReportReviewUpdate,
)
from backend.clash_report_service import (
    apply_clash_report_resolution_candidate,
    create_clash_report,
    generate_clash_report_resolution_candidates,
    update_clash_report,
)
from backend.database import Base
from backend.enrollment_conflict_graph import build_enrollment_conflict_analysis
from backend.faculty_schemas import FacultyAssignmentCreate
from backend.faculty_service import create_faculty_assignment
from backend.models import (
    AcademicTerm,
    CourseOffering,
    FacultyAvailabilityWindow,
    FacultyClassAssignment,
    FacultyTeachingProfile,
    StudentEnrollment,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.scheduling_policy import allowed_days_for
from backend.schemas import TimetableTimeChangeRequest
from backend.student_resolution_applier import (
    redo_student_resolution,
    undo_student_resolution,
)
from backend.timetable_generation_schemas import (
    TimetableGenerationApplyResponse,
    TimetableGenerationPreviewResponse,
)
from backend.timetable_generation_service import (
    apply_timetable_generation,
    preview_timetable_generation,
)
from backend.timetable_time_service import apply_manual_time_change


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
    email: str,
    role: str,
    *,
    full_name: str | None = None,
) -> User:
    user = User(
        email=email,
        full_name=full_name or email.split("@")[0].replace(".", " ").title(),
        password_hash=hash_password("Password123"),
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def add_faculty(
    db,
    email: str,
    *,
    full_name: str,
    designation: str = "lecturer",
) -> User:
    faculty = add_user(
        db,
        email,
        "faculty",
        full_name=full_name,
    )
    db.add(
        FacultyTeachingProfile(
            user_id=faculty.id,
            designation=designation,
        )
    )
    db.flush()
    return faculty


def add_term(db, code: str = "PLAN-2027") -> AcademicTerm:
    term = AcademicTerm(
        code=code,
        name=code,
        status="planning",
    )
    db.add(term)
    db.flush()
    return term


def add_offering(
    db,
    *,
    term: AcademicTerm,
    faculty: User,
    course_code: str,
    semester: int,
    section: str = "A",
    class_type: str = "lecture",
    duration_minutes: int = 60,
    room: str = "R-101",
) -> CourseOffering:
    offering = CourseOffering(
        term_id=term.id,
        course_code=course_code,
        course_name=f"{course_code} Course",
        semester=semester,
        section=section,
        class_type=class_type,
        duration_minutes=duration_minutes,
        room=room,
    )
    db.add(offering)
    db.add(
        FacultyClassAssignment(
            term_id=term.id,
            faculty_user_id=faculty.id,
            course_code=course_code,
            section=section,
            semester=str(semester),
        )
    )
    db.flush()
    return offering


def add_availability(
    db,
    *,
    term: AcademicTerm,
    faculty: User,
    day: str,
    start: str,
    end: str,
) -> FacultyAvailabilityWindow:
    window = FacultyAvailabilityWindow(
        term_id=term.id,
        faculty_user_id=faculty.id,
        day=day,
        start_time=start,
        end_time=end,
    )
    db.add(window)
    db.flush()
    return window


def test_authoritative_semester_day_rules():
    assert allowed_days_for(1, "lecture") == ("Monday", "Wednesday")
    assert allowed_days_for(3, "lab") == ("Thursday",)
    assert allowed_days_for(5, "lecture") == ("Monday", "Wednesday")
    assert allowed_days_for(7, "lab") == ("Thursday",)
    assert allowed_days_for(2, "lecture") == ("Tuesday", "Thursday")
    assert allowed_days_for(4, "lab") == ("Friday",)
    assert allowed_days_for(6, "lecture") == ("Tuesday", "Thursday")
    assert allowed_days_for(8, "lab") == ("Friday",)

    with pytest.raises(ValueError):
        allowed_days_for(9, "lecture")
    with pytest.raises(ValueError):
        allowed_days_for(1, "seminar")


def test_numeric_same_semester_different_sections_is_a_hard_clash():
    first = TimetableEntry(
        id=1,
        semester="3",
        section="A",
        course_code="CS-301",
        day="Monday",
        start_time="08:00",
        end_time="09:00",
    )
    second = TimetableEntry(
        id=2,
        semester="3",
        section="B",
        course_code="CS-302",
        day="Monday",
        start_time="08:30",
        end_time="09:30",
    )

    clashes = detect_clashes([first, second])
    assert any(clash["type"] == "semester" for clash in clashes)

    first.semester = "Fall 2026"
    second.semester = "Fall 2026"
    assert not any(
        clash["type"] == "semester"
        for clash in detect_clashes([first, second])
    )


def test_preview_generates_odd_lecture_sessions_and_does_not_mutate():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        faculty = add_faculty(
            db,
            "ada@example.edu",
            full_name="Ada Lecturer",
        )
        add_offering(
            db,
            term=term,
            faculty=faculty,
            course_code="AI-301",
            semester=3,
            room="R-301",
        )
        for day in ("Monday", "Wednesday"):
            add_availability(
                db,
                term=term,
                faculty=faculty,
                day=day,
                start="08:00",
                end="12:00",
            )
        db.commit()

        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )

        assert preview["complete"] is True
        assert preview["status"] == "READY"
        assert preview["proposed_count"] == 2
        assert {
            proposal["day"]
            for proposal in preview["proposals"]
        } == {"Monday", "Wednesday"}
        assert db.query(TimetableEntry).count() == 0


def test_preview_blocks_when_true_faculty_availability_is_missing():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        faculty = add_faculty(
            db,
            "missing@example.edu",
            full_name="Missing Availability",
        )
        add_offering(
            db,
            term=term,
            faculty=faculty,
            course_code="CS-201",
            semester=2,
            room="R-201",
        )
        db.commit()

        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )

        assert preview["complete"] is False
        assert preview["status"] == "BLOCKED"
        assert any(
            "availability" in message.lower()
            for message in (
                preview["readiness_errors"]
                + preview["unscheduled"]
            )
        )


def test_roomless_offering_returns_valid_blocked_preview_without_invalid_proposal():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        faculty = add_faculty(
            db,
            "roomless@example.edu",
            full_name="Roomless Lecturer",
        )
        add_offering(
            db,
            term=term,
            faculty=faculty,
            course_code="CS-250",
            semester=2,
            room=None,
        )
        for day in ("Tuesday", "Thursday"):
            add_availability(
                db,
                term=term,
                faculty=faculty,
                day=day,
                start="08:00",
                end="12:00",
            )
        db.commit()

        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )

        assert preview["status"] == "BLOCKED"
        assert preview["complete"] is False
        assert preview["proposals"] == []
        assert any(
            "room" in message.lower()
            for message in preview["readiness_errors"]
        )
        TimetableGenerationPreviewResponse.model_validate(preview)


def test_generator_separates_same_semester_subjects():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        first_faculty = add_faculty(
            db,
            "first@example.edu",
            full_name="First Lecturer",
        )
        second_faculty = add_faculty(
            db,
            "second@example.edu",
            full_name="Second Lecturer",
        )
        add_offering(
            db,
            term=term,
            faculty=first_faculty,
            course_code="CS-101",
            semester=1,
            room="R-101",
        )
        add_offering(
            db,
            term=term,
            faculty=second_faculty,
            course_code="CS-102",
            semester=1,
            room="R-102",
        )
        for faculty in (first_faculty, second_faculty):
            for day in ("Monday", "Wednesday"):
                add_availability(
                    db,
                    term=term,
                    faculty=faculty,
                    day=day,
                    start="08:00",
                    end="12:00",
                )
        db.commit()

        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        assert preview["complete"] is True

        for day in ("Monday", "Wednesday"):
            starts = [
                proposal["start_time"]
                for proposal in preview["proposals"]
                if proposal["day"] == day
            ]
            assert len(starts) == 2
            assert len(set(starts)) == 2


def test_generation_preview_is_stale_after_availability_change_and_fresh_apply_is_idempotent():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        faculty = add_faculty(
            db,
            "stale@example.edu",
            full_name="Stale Lecturer",
        )
        add_offering(
            db,
            term=term,
            faculty=faculty,
            course_code="CS-401",
            semester=4,
            room="R-401",
        )
        windows = []
        for day in ("Tuesday", "Thursday"):
            windows.append(
                add_availability(
                    db,
                    term=term,
                    faculty=faculty,
                    day=day,
                    start="08:00",
                    end="12:00",
                )
            )
        db.commit()

        old_preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        windows[0].end_time = "11:00"
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            apply_timetable_generation(
                db,
                term_id=term.id,
                preview_id=old_preview["preview_id"],
            )
        assert exc_info.value.status_code == 409
        assert "stale" in str(exc_info.value.detail).lower()

        fresh = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        applied = apply_timetable_generation(
            db,
            term_id=term.id,
            preview_id=fresh["preview_id"],
        )
        assert applied["created_count"] == 2
        TimetableGenerationApplyResponse.model_validate(applied)

        already_satisfied = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        assert already_satisfied["complete"] is True
        assert already_satisfied["proposed_count"] == 0
        second_apply = apply_timetable_generation(
            db,
            term_id=term.id,
            preview_id=already_satisfied["preview_id"],
        )
        assert second_apply["created_count"] == 0


def test_manual_move_cannot_break_semester_day_policy():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        faculty = add_faculty(
            db,
            "manual@example.edu",
            full_name="Manual Lecturer",
        )
        add_offering(
            db,
            term=term,
            faculty=faculty,
            course_code="CS-501",
            semester=5,
            room="R-501",
        )
        for day in ("Monday", "Wednesday"):
            add_availability(
                db,
                term=term,
                faculty=faculty,
                day=day,
                start="08:00",
                end="12:00",
            )
        db.commit()
        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        apply_timetable_generation(
            db,
            term_id=term.id,
            preview_id=preview["preview_id"],
        )
        entry = (
            db.query(TimetableEntry)
            .filter(
                TimetableEntry.term_id == term.id,
                TimetableEntry.day == "Monday",
            )
            .one()
        )

        with pytest.raises(HTTPException) as exc_info:
            apply_manual_time_change(
                db,
                entry_id=entry.id,
                request=TimetableTimeChangeRequest(
                    day="Thursday",
                    start_time="09:00",
                    end_time="10:00",
                ),
            )
        assert exc_info.value.status_code == 409
        assert "must be scheduled" in str(exc_info.value.detail)


def test_planning_offering_cannot_be_allocated_to_two_teachers():
    Session = create_session()
    with Session() as db:
        term = add_term(db)
        first = add_faculty(
            db,
            "owner@example.edu",
            full_name="Owner Lecturer",
        )
        second = add_faculty(
            db,
            "other@example.edu",
            full_name="Other Lecturer",
        )
        offering = CourseOffering(
            term_id=term.id,
            course_code="AI-450",
            course_name="AI 450",
            semester=4,
            section="A",
            class_type="lecture",
            duration_minutes=60,
            room="R-450",
        )
        db.add(offering)
        db.commit()

        first_assignment = create_faculty_assignment(
            db,
            created_by_user_id=first.id,
            request=FacultyAssignmentCreate(
                faculty_user_id=first.id,
                term_id=term.id,
                course_code="AI-450",
                section="A",
                semester="4",
            ),
        )
        assert first_assignment["faculty_user_id"] == first.id

        with pytest.raises(HTTPException) as exc_info:
            create_faculty_assignment(
                db,
                created_by_user_id=second.id,
                request=FacultyAssignmentCreate(
                    faculty_user_id=second.id,
                    term_id=term.id,
                    course_code="AI-450",
                    section="A",
                    semester="4",
                ),
            )
        assert exc_info.value.status_code == 409
        assert "already allocated" in str(exc_info.value.detail).lower()


def test_repeat_student_clash_resolves_with_policy_availability_and_undo_redo():
    Session = create_session()
    with Session() as db:
        term = add_term(db, "REPEAT-2027")
        repeat_faculty = add_faculty(
            db,
            "repeat.faculty@example.edu",
            full_name="Repeat Lecturer",
        )
        current_faculty = add_faculty(
            db,
            "current.faculty@example.edu",
            full_name="Current Lecturer",
        )

        add_offering(
            db,
            term=term,
            faculty=repeat_faculty,
            course_code="OLD-301",
            semester=3,
            room="R-301",
        )
        add_offering(
            db,
            term=term,
            faculty=current_faculty,
            course_code="CUR-501",
            semester=5,
            room="R-501",
        )

        add_availability(
            db,
            term=term,
            faculty=repeat_faculty,
            day="Monday",
            start="08:00",
            end="11:00",
        )
        add_availability(
            db,
            term=term,
            faculty=repeat_faculty,
            day="Wednesday",
            start="08:00",
            end="09:00",
        )
        add_availability(
            db,
            term=term,
            faculty=current_faculty,
            day="Monday",
            start="08:00",
            end="09:00",
        )
        add_availability(
            db,
            term=term,
            faculty=current_faculty,
            day="Wednesday",
            start="10:00",
            end="11:00",
        )
        db.commit()

        preview = preview_timetable_generation(
            db,
            term_id=term.id,
        )
        assert preview["complete"] is True
        apply_timetable_generation(
            db,
            term_id=term.id,
            preview_id=preview["preview_id"],
        )

        entries = list(
            db.query(TimetableEntry)
            .filter(TimetableEntry.term_id == term.id)
            .order_by(TimetableEntry.id)
        )
        repeat_monday = next(
            entry
            for entry in entries
            if entry.course_code == "OLD-301"
            and entry.day == "Monday"
        )
        current_monday = next(
            entry
            for entry in entries
            if entry.course_code == "CUR-501"
            and entry.day == "Monday"
        )
        assert repeat_monday.start_time == "08:00"
        assert current_monday.start_time == "08:00"

        term.status = "active"
        term.activated_at = datetime.now(UTC).replace(tzinfo=None)

        student = add_user(
            db,
            "repeat.student@example.edu",
            "student",
            full_name="Repeat Student",
        )
        db.add(
            StudentProfile(
                user_id=student.id,
                registration_number="REPEAT-001",
                department="Computer Science",
                program="BS Computer Science",
                batch="2024",
                current_semester=5,
                section="A",
                academic_status="active",
                is_verified=True,
                onboarding_completed=True,
            )
        )
        db.add_all(
            [
                StudentEnrollment(
                    term_id=term.id,
                    user_id=student.id,
                    course_code="OLD-301",
                    section="A",
                    semester="3",
                ),
                StudentEnrollment(
                    term_id=term.id,
                    user_id=student.id,
                    course_code="CUR-501",
                    section="A",
                    semester="5",
                ),
            ]
        )
        coordinator = add_user(
            db,
            "coordinator@example.edu",
            "coordinator",
            full_name="Coordinator",
        )
        db.commit()

        entries = list(
            db.query(TimetableEntry)
            .filter(TimetableEntry.term_id == term.id)
            .order_by(TimetableEntry.id)
        )
        analysis = build_enrollment_conflict_analysis(
            db,
            entries,
            term_id=term.id,
        )
        confirmed = [
            risk
            for risk in analysis["risks"]
            if risk["risk_level"] == "confirmed"
        ]
        assert len(confirmed) == 1
        assert confirmed[0]["affected_student_count"] == 1

        report = create_clash_report(
            db,
            student_user_id=student.id,
            request=ClashReportCreate(
                timetable_entry_ids=[
                    repeat_monday.id,
                    current_monday.id,
                ],
                notes="Repeat course overlaps my current Semester 5 subject.",
            ),
        )
        update_clash_report(
            db,
            report_id=report["id"],
            actor_user_id=coordinator.id,
            request=ClashReportReviewUpdate(
                status="under_review",
            ),
        )

        result = generate_clash_report_resolution_candidates(
            db,
            report_id=report["id"],
            target_entry_id=repeat_monday.id,
            limit=100,
            include_rejected_limit=100,
        )
        applicable = [
            candidate
            for candidate in result["candidates"]
            if candidate["status"] in {"SAFE", "CONDITIONALLY_SAFE"}
        ]
        assert applicable
        candidate = applicable[0]
        assert candidate["move_to"]["day"] in {"Monday", "Wednesday"}
        assert candidate["move_to"]["day"] == "Monday"
        assert candidate["move_to"]["start_time"] >= "09:00"
        assert not any(
            "hard-unavailability calendar is not modeled" in item
            for item in candidate["missing_data"]
        )
        assert not any(
            "true availability" in item.lower()
            for item in candidate["missing_data"]
        )

        applied = apply_clash_report_resolution_candidate(
            db,
            report_id=report["id"],
            candidate_id=candidate["candidate_id"],
            actor_user_id=coordinator.id,
            request=ClashReportResolutionApplyRequest(
                target_entry_id=repeat_monday.id,
                resolution_note=(
                    "Moved the repeated Semester 3 subject to a safe "
                    "Monday slot inside faculty availability."
                ),
                confirm_conditional=True,
            ),
        )
        assert applied["report_status"] == "resolved"
        assert applied["change_id"] > 0

        moved = db.get(TimetableEntry, repeat_monday.id)
        assert moved.start_time >= "09:00"

        undone = undo_student_resolution(
            db,
            change_id=applied["change_id"],
            actor_user_id=coordinator.id,
        )
        assert undone["report_status"] == "under_review"
        restored = db.get(TimetableEntry, repeat_monday.id)
        assert restored.day == "Monday"
        assert restored.start_time == "08:00"

        redone = redo_student_resolution(
            db,
            change_id=applied["change_id"],
            actor_user_id=coordinator.id,
        )
        assert redone["report_status"] == "resolved"
        redone_entry = db.get(TimetableEntry, repeat_monday.id)
        assert redone_entry.start_time >= "09:00"
