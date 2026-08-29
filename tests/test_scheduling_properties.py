from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from hypothesis import example, given, settings, strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.timetable_generation_service as generation_service
from backend.clash_detector import detect_clashes
from backend.concurrency import acquire_timetable_write_lock
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
from backend.scheduling_policy import (
    BlockedPeriod,
    SchedulingPolicy,
    allowed_days_for,
    minutes_to_time,
    time_to_minutes,
)
from backend.timetable_generation_service import (
    apply_timetable_generation,
    preview_timetable_generation,
)


PURE_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    derandomize=True,
)

DB_SETTINGS = settings(
    max_examples=24,
    deadline=None,
    derandomize=True,
)


@PURE_SETTINGS
@given(st.integers(min_value=0, max_value=(24 * 60) - 1))
def test_minute_time_conversion_round_trips(minute_value: int):
    rendered = minutes_to_time(minute_value)
    assert time_to_minutes(rendered) == minute_value


@PURE_SETTINGS
@given(
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
)
def test_hhmm_time_conversion_round_trips(hour: int, minute: int):
    value = f"{hour:02d}:{minute:02d}"
    assert minutes_to_time(time_to_minutes(value)) == value


@PURE_SETTINGS
@given(
    semester=st.integers(min_value=1, max_value=8),
    class_type=st.sampled_from(("lecture", "lab")),
)
def test_semester_day_policy_holds_for_all_supported_inputs(
    semester: int,
    class_type: str,
):
    actual = allowed_days_for(semester, class_type)

    if semester % 2:
        expected = (
            ("Monday", "Wednesday")
            if class_type == "lecture"
            else ("Thursday",)
        )
    else:
        expected = (
            ("Tuesday", "Thursday")
            if class_type == "lecture"
            else ("Friday",)
        )

    assert actual == expected


@PURE_SETTINGS
@given(
    duration=st.integers(min_value=30, max_value=240),
)
def test_generated_policy_slots_are_unique_aligned_and_valid(duration: int):
    policy = SchedulingPolicy()
    slots = policy.generate_slots(duration_minutes=duration)

    assert len(slots) <= policy.maximum_candidates_per_entry
    assert len(
        {
            (slot["day"], slot["start_time"], slot["end_time"])
            for slot in slots
        }
    ) == len(slots)

    opening = time_to_minutes(policy.opens_at)
    for slot in slots:
        start = time_to_minutes(slot["start_time"])
        end = time_to_minutes(slot["end_time"])
        assert policy.validate_slot(**slot) == []
        assert end - start == duration
        assert (start - opening) % policy.slot_interval_minutes == 0


@st.composite
def _blocked_period_case(draw):
    day = draw(
        st.sampled_from(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        )
    )
    start = draw(st.integers(min_value=8 * 60, max_value=19 * 60))
    maximum_length = min(180, (20 * 60) - start)
    length = draw(st.integers(min_value=30, max_value=maximum_length))
    duration = draw(st.sampled_from((30, 45, 60, 90, 120)))
    return day, start, start + length, duration


@PURE_SETTINGS
@given(_blocked_period_case())
def test_generated_slots_never_cross_configured_blocked_periods(case):
    day, blocked_start, blocked_end, duration = case
    policy = SchedulingPolicy(
        blocked_periods=(
            BlockedPeriod(
                day=day,
                start_time=minutes_to_time(blocked_start),
                end_time=minutes_to_time(blocked_end),
                reason="Qualification block",
            ),
        )
    )

    slots = policy.generate_slots(duration_minutes=duration)

    for slot in slots:
        if slot["day"] != day:
            continue
        start = time_to_minutes(slot["start_time"])
        end = time_to_minutes(slot["end_time"])
        assert not (start < blocked_end and blocked_start < end)


def _engine_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    return engine, Session


def _seed_single_offering(
    db,
    *,
    semester: int,
    class_type: str,
    duration_minutes: int,
):
    term = AcademicTerm(
        code="QUAL-PLAN",
        name="Qualification Planning Term",
        status="planning",
    )
    db.add(term)
    db.flush()

    faculty = User(
        email="property.faculty@example.edu",
        full_name="Property Faculty",
        password_hash="qualification-only-placeholder",
        role="faculty",
        is_active=True,
        must_change_password=False,
    )
    db.add(faculty)
    db.flush()

    db.add(
        FacultyTeachingProfile(
            user_id=faculty.id,
            designation="lecturer",
        )
    )

    offering = CourseOffering(
        term_id=term.id,
        course_code="QUAL-101",
        course_name="Qualification Course",
        semester=semester,
        section="A",
        class_type=class_type,
        duration_minutes=duration_minutes,
        room="Q-101",
    )
    db.add(offering)
    db.flush()

    db.add(
        FacultyClassAssignment(
            term_id=term.id,
            faculty_user_id=faculty.id,
            course_code=offering.course_code,
            section=offering.section,
            semester=str(semester),
        )
    )

    required_days = allowed_days_for(semester, class_type)
    for day in required_days:
        db.add(
            FacultyAvailabilityWindow(
                term_id=term.id,
                faculty_user_id=faculty.id,
                day=day,
                start_time="08:00",
                end_time="16:00",
            )
        )

    db.commit()
    return term, faculty, offering, required_days


@DB_SETTINGS
@example(semester=1, class_type="lecture", duration_minutes=30)
@example(semester=8, class_type="lab", duration_minutes=240)
@given(
    semester=st.integers(min_value=1, max_value=8),
    class_type=st.sampled_from(("lecture", "lab")),
    duration_minutes=st.sampled_from((30, 45, 60, 75, 90, 120, 180, 240)),
)
def test_generated_timetable_preserves_institutional_invariants(
    semester: int,
    class_type: str,
    duration_minutes: int,
):
    engine, Session = _engine_and_session()
    try:
        with Session() as db:
            term, faculty, offering, required_days = _seed_single_offering(
                db,
                semester=semester,
                class_type=class_type,
                duration_minutes=duration_minutes,
            )

            first_preview = preview_timetable_generation(
                db,
                term_id=term.id,
            )
            second_preview = preview_timetable_generation(
                db,
                term_id=term.id,
            )

            assert first_preview == second_preview
            assert first_preview["complete"] is True
            assert first_preview["status"] == "READY"
            assert first_preview["readiness_errors"] == []
            assert first_preview["unscheduled"] == []
            assert first_preview["proposed_count"] == len(required_days)
            assert db.query(TimetableEntry).count() == 0

            proposals = first_preview["proposals"]
            assert {proposal["day"] for proposal in proposals} == set(required_days)

            for proposal in proposals:
                assert proposal["faculty_user_id"] == faculty.id
                assert proposal["faculty_name"] == faculty.full_name
                assert proposal["course_code"] == offering.course_code
                assert proposal["semester"] == semester
                assert proposal["section"] == "A"
                assert proposal["class_type"] == class_type
                assert proposal["room"] == "Q-101"
                assert proposal["duration_minutes"] == duration_minutes
                assert (
                    time_to_minutes(proposal["end_time"])
                    - time_to_minutes(proposal["start_time"])
                ) == duration_minutes
                assert time_to_minutes(proposal["start_time"]) >= 8 * 60
                assert time_to_minutes(proposal["end_time"]) <= 16 * 60

            applied = apply_timetable_generation(
                db,
                term_id=term.id,
                preview_id=first_preview["preview_id"],
            )
            assert applied["created_count"] == len(required_days)

            entries = list(
                db.query(TimetableEntry)
                .filter(TimetableEntry.term_id == term.id)
                .order_by(TimetableEntry.id)
            )
            assert len(entries) == len(required_days)
            assert detect_clashes(entries) == []

            for entry in entries:
                assert entry.day in required_days
                assert entry.faculty == faculty.full_name
                assert entry.room == "Q-101"
                assert entry.source == "generated"
                assert (
                    time_to_minutes(entry.end_time)
                    - time_to_minutes(entry.start_time)
                ) == duration_minutes

            satisfied = preview_timetable_generation(
                db,
                term_id=term.id,
            )
            assert satisfied["complete"] is True
            assert satisfied["proposed_count"] == 0
            assert satisfied["existing_satisfied_count"] == len(required_days)

            second_apply = apply_timetable_generation(
                db,
                term_id=term.id,
                preview_id=satisfied["preview_id"],
            )
            assert second_apply["created_count"] == 0
            assert (
                db.query(TimetableEntry)
                .filter(TimetableEntry.term_id == term.id)
                .count()
            ) == len(required_days)
    finally:
        engine.dispose()


def test_postgresql_advisory_lock_failure_is_not_silently_swallowed():
    session = Mock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.side_effect = RuntimeError("simulated advisory lock failure")

    with pytest.raises(RuntimeError, match="advisory lock failure"):
        acquire_timetable_write_lock(session)

    session.execute.assert_called_once()


def test_generation_apply_rolls_back_when_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    db = Mock()
    db.flush.side_effect = RuntimeError("simulated persistence failure")

    monkeypatch.setattr(
        generation_service,
        "_planning_term",
        lambda _db, _term_id: SimpleNamespace(id=_term_id, status="planning"),
    )
    monkeypatch.setattr(
        generation_service,
        "preview_timetable_generation",
        lambda _db, *, term_id: {
            "preview_id": "stable-preview",
            "complete": True,
            "existing_satisfied_count": 0,
            "proposals": [
                {
                    "offering_id": 1,
                    "faculty_user_id": 1,
                    "faculty_name": "Failure Faculty",
                    "course_code": "FAIL-101",
                    "course_name": "Failure Injection",
                    "semester": 1,
                    "section": "A",
                    "class_type": "lecture",
                    "room": "F-101",
                    "day": "Monday",
                    "start_time": "08:00",
                    "end_time": "09:00",
                    "duration_minutes": 60,
                }
            ],
        },
    )

    with pytest.raises(RuntimeError, match="persistence failure"):
        apply_timetable_generation(
            db,
            term_id=1,
            preview_id="stable-preview",
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
