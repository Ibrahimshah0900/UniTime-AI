from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import (
    AcademicTerm,
    StudentEnrollment,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.safe_candidate_service import generate_safe_candidates
from backend.scheduling_policy import (
    BlockedPeriod,
    SchedulingPolicy,
    time_to_minutes,
)


def create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_student(db, number: str, course_codes: tuple[str, ...]) -> User:
    user = User(
        email=f"{number.lower()}@example.edu",
        full_name=number,
        password_hash="not-used-by-candidate-tests",
        role="student",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        StudentProfile(
            user_id=user.id,
            registration_number=number,
            department="Computing",
            program="BS AI",
            batch="2026",
            current_semester=3,
            section="A",
            academic_status="active",
            is_verified=True,
            onboarding_completed=True,
        )
    )
    for course_code in course_codes:
        db.add(
            StudentEnrollment(
                term_id=1,
                user_id=user.id,
                course_code=course_code,
                section={"AI-232": "A", "CS-242": "B", "PHY-201": "C"}[course_code],
                semester="Fall 2026",
            )
        )
    db.flush()
    return user


def seed_candidate_scenario(db) -> tuple[TimetableEntry, TimetableEntry, TimetableEntry]:
    db.add(
        AcademicTerm(
            code="FALL-2026",
            name="Fall 2026",
            status="active",
        )
    )
    db.flush()
    target = TimetableEntry(
        term_id=1,
        course_code="AI-232",
        course_name="Artificial Intelligence",
        semester="Fall 2026",
        section="A",
        faculty="Dr Ada",
        room="R-101",
        day="Monday",
        start_time="10:00",
        end_time="11:30",
    )
    reported_peer = TimetableEntry(
        term_id=1,
        course_code="CS-242",
        course_name="Algorithms",
        semester="Fall 2026",
        section="B",
        faculty="Dr Turing",
        room="R-102",
        day="Monday",
        start_time="10:30",
        end_time="12:00",
    )
    destination_blocker = TimetableEntry(
        term_id=1,
        course_code="PHY-201",
        course_name="Physics",
        semester="Fall 2026",
        section="C",
        faculty="Dr Curie",
        room="R-101",
        day="Tuesday",
        start_time="09:00",
        end_time="10:30",
    )
    db.add_all([target, reported_peer, destination_blocker])
    db.flush()
    create_student(db, "FA23-001", ("AI-232", "CS-242", "PHY-201"))
    create_student(db, "FA23-002", ("AI-232",))
    db.commit()
    return target, reported_peer, destination_blocker


def candidate_policy() -> SchedulingPolicy:
    return SchedulingPolicy(
        operating_days=("Monday", "Tuesday"),
        opens_at="08:00",
        closes_at="14:00",
        slot_interval_minutes=30,
        blocked_periods=(
            BlockedPeriod(
                day="Monday",
                start_time="08:00",
                end_time="09:00",
                reason="Institutional assembly",
            ),
        ),
        maximum_candidates_per_entry=50,
    )


def load_entries(db) -> list[TimetableEntry]:
    return list(db.scalars(select(TimetableEntry).order_by(TimetableEntry.id)).all())


def test_policy_validates_time_and_keeps_blocked_slots_auditable():
    policy = candidate_policy()

    assert time_to_minutes("09:30") == 570
    assert policy.validate_slot(
        day="Monday",
        start_time="08:00",
        end_time="09:30",
    ) == ["Slot overlaps blocked period: Institutional assembly."]
    valid_monday_starts = {
        slot["start_time"]
        for slot in policy.generate_slots(duration_minutes=90)
        if slot["day"] == "Monday"
    }
    auditable_monday_starts = {
        slot["start_time"]
        for slot in policy.generate_slots(
            duration_minutes=90,
            include_blocked=True,
        )
        if slot["day"] == "Monday"
    }
    assert valid_monday_starts.isdisjoint({"08:00", "08:30"})
    assert auditable_monday_starts.issuperset({"08:00", "08:30"})


def test_candidates_preserve_duration_are_deterministic_and_do_not_mutate_timetable():
    Session = create_session()
    with Session() as db:
        target, peer, _ = seed_candidate_scenario(db)
        entries = load_entries(db)
        before = [
            (entry.id, entry.day, entry.start_time, entry.end_time, entry.room)
            for entry in entries
        ]

        first = generate_safe_candidates(
            db,
            entries=entries,
            target_entry_ids=[target.id],
            report_entry_ids=[target.id, peer.id],
            policy=candidate_policy(),
            limit=100,
            include_rejected_limit=100,
        )
        second = generate_safe_candidates(
            db,
            entries=entries,
            target_entry_ids=[target.id],
            report_entry_ids=[target.id, peer.id],
            policy=candidate_policy(),
            limit=100,
            include_rejected_limit=100,
        )

        assert first == second
        assert first["candidates"]
        assert all(candidate["duration_minutes"] == 90 for candidate in first["candidates"])
        assert all(candidate["status"] != "REJECTED" for candidate in first["candidates"])
        assert all(
            candidate["impact"]["new_confirmed_conflicts"] == 0
            for candidate in first["candidates"]
        )
        assert all(
            next(
                check for check in candidate["checks"]
                if check["name"] == "original_report_overlap"
            )["status"] == "PASS"
            for candidate in first["candidates"]
        )
        assert all(candidate["score_components"] for candidate in first["candidates"])
        assert all(candidate["status"] == "CONDITIONALLY_SAFE" for candidate in first["candidates"])
        assert any(
            "blocked period" in " ".join(candidate["rejection_reasons"]).lower()
            for candidate in first["rejected_candidates"]
        )
        assert any(
            "new confirmed student conflict" in " ".join(candidate["rejection_reasons"]).lower()
            for candidate in first["rejected_candidates"]
        )

        after_entries = load_entries(db)
        after = [
            (entry.id, entry.day, entry.start_time, entry.end_time, entry.room)
            for entry in after_entries
        ]
        assert after == before


def test_missing_enrollment_or_assignment_data_is_never_presented_as_safe():
    Session = create_session()
    with Session() as db:
        target, peer, _ = seed_candidate_scenario(db)
        db.query(StudentEnrollment).filter(
            StudentEnrollment.course_code == "AI-232"
        ).delete(synchronize_session=False)
        target.room = None
        target.faculty = "TBA"
        db.commit()

        result = generate_safe_candidates(
            db,
            entries=load_entries(db),
            target_entry_ids=[target.id],
            report_entry_ids=[target.id, peer.id],
            policy=candidate_policy(),
            limit=100,
        )

        assert result["candidates"]
        assert all(candidate["status"] == "INSUFFICIENT_DATA" for candidate in result["candidates"])
        missing = " ".join(result["candidates"][0]["missing_data"])
        assert "No room" in missing
        assert "Faculty identity" in missing
        assert "enrollment coverage" in missing
        assert all(
            candidate["actionable_without_confirmation"] is False
            for candidate in result["candidates"]
        )


def test_candidate_identity_changes_when_enrollment_safety_state_changes():
    Session = create_session()
    with Session() as db:
        target, peer, _ = seed_candidate_scenario(db)
        first = generate_safe_candidates(
            db,
            entries=load_entries(db),
            target_entry_ids=[target.id],
            report_entry_ids=[target.id, peer.id],
            policy=candidate_policy(),
            limit=100,
        )
        first_ids = {
            tuple(candidate["move_to"].values()): candidate["candidate_id"]
            for candidate in first["candidates"]
        }

        create_student(db, "FA23-003", ("AI-232",))
        db.commit()
        second = generate_safe_candidates(
            db,
            entries=load_entries(db),
            target_entry_ids=[target.id],
            report_entry_ids=[target.id, peer.id],
            policy=candidate_policy(),
            limit=100,
        )
        second_ids = {
            tuple(candidate["move_to"].values()): candidate["candidate_id"]
            for candidate in second["candidates"]
        }

        shared_moves = first_ids.keys() & second_ids.keys()
        assert shared_moves
        assert all(first_ids[move] != second_ids[move] for move in shared_moves)
