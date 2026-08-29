from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from backend.concurrency import acquire_timetable_write_lock
from backend.database import SessionLocal, engine
from backend.models import (
    AcademicTerm,
    CourseOffering,
    FacultyAvailabilityWindow,
    FacultyClassAssignment,
    FacultyTeachingProfile,
    TimetableEntry,
    User,
)
from backend.timetable_generation_service import (
    apply_timetable_generation,
    preview_timetable_generation,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATABASE_TESTS") != "1",
    reason=(
        "Live PostgreSQL concurrency tests are enabled explicitly "
        "in disposable CI databases."
    ),
)


def _backend_pid(db) -> int:
    return int(db.execute(text("SELECT pg_backend_pid()")).scalar_one())


def _set_short_lock_timeout(db) -> None:
    db.execute(text("SET LOCAL lock_timeout = '300ms'"))


def _seed_generation_case() -> tuple[int, str]:
    token = uuid4().hex

    with SessionLocal() as db:
        term = AcademicTerm(
            code=f"CONC-{token[:12]}",
            name="Concurrency Qualification Term",
            status="planning",
        )
        db.add(term)
        db.flush()

        faculty = User(
            email=f"concurrency-{token}@example.edu",
            full_name="Concurrency Faculty",
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
            course_code=f"QUAL-{token[:8]}",
            course_name="Concurrency Qualification Course",
            semester=1,
            section="A",
            class_type="lecture",
            duration_minutes=60,
            room=f"Q-{token[:8]}",
        )
        db.add(offering)
        db.flush()

        db.add(
            FacultyClassAssignment(
                term_id=term.id,
                faculty_user_id=faculty.id,
                course_code=offering.course_code,
                section=offering.section,
                semester="1",
            )
        )

        for day in ("Monday", "Wednesday"):
            db.add(
                FacultyAvailabilityWindow(
                    term_id=term.id,
                    faculty_user_id=faculty.id,
                    day=day,
                    start_time="08:00",
                    end_time="12:00",
                )
            )

        db.commit()
        term_id = term.id

    with SessionLocal() as db:
        preview = preview_timetable_generation(
            db,
            term_id=term_id,
        )

    assert preview["complete"] is True
    assert preview["proposed_count"] == 2
    return term_id, preview["preview_id"]


def _apply_generation_preview(
    barrier: Barrier,
    *,
    term_id: int,
    preview_id: str,
) -> tuple[str, int]:
    with SessionLocal() as db:
        barrier.wait(timeout=5)
        acquire_timetable_write_lock(db)

        try:
            result = apply_timetable_generation(
                db,
                term_id=term_id,
                preview_id=preview_id,
            )
        except HTTPException as exc:
            return "http_error", exc.status_code

        return "applied", int(result["created_count"])


def test_postgresql_timetable_advisory_lock_serializes_independent_sessions():
    assert engine.dialect.name == "postgresql"

    with SessionLocal() as first, SessionLocal() as second:
        first_pid = _backend_pid(first)
        second_pid = _backend_pid(second)
        assert first_pid != second_pid

        acquire_timetable_write_lock(first)

        _set_short_lock_timeout(second)
        with pytest.raises(DBAPIError):
            acquire_timetable_write_lock(second)

        # A lock timeout aborts PostgreSQL's current transaction.
        # Roll back before reusing the second session.
        second.rollback()

        # The advisory lock is transaction-scoped, so committing the
        # first writer must release it.
        first.commit()

        _set_short_lock_timeout(second)
        acquire_timetable_write_lock(second)
        second.rollback()


def test_postgresql_timetable_advisory_lock_releases_on_rollback():
    assert engine.dialect.name == "postgresql"

    with SessionLocal() as first, SessionLocal() as second:
        assert _backend_pid(first) != _backend_pid(second)

        acquire_timetable_write_lock(first)
        first.rollback()

        _set_short_lock_timeout(second)
        acquire_timetable_write_lock(second)
        second.commit()

def test_concurrent_generation_apply_serializes_and_rejects_stale_preview():
    assert engine.dialect.name == "postgresql"

    term_id, preview_id = _seed_generation_case()
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _apply_generation_preview,
                barrier,
                term_id=term_id,
                preview_id=preview_id,
            )
            for _ in range(2)
        ]

        outcomes = sorted(
            future.result(timeout=10)
            for future in futures
        )

    assert outcomes == [
        ("applied", 2),
        ("http_error", 409),
    ]

    with SessionLocal() as db:
        entry_count = db.scalar(
            select(func.count())
            .select_from(TimetableEntry)
            .where(TimetableEntry.term_id == term_id)
        )

    assert entry_count == 2
