from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.demo_data import (
    DemoDataConfig,
    assert_demo_database_is_pristine,
    benchmark_demo_resolver,
    generate_demo_data,
    is_safe_demo_database_path,
)
from backend.models import AcademicTerm, StudentEnrollment, StudentProfile, TimetableEntry, User


def create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(
            AcademicTerm(
                id=1,
                code="LEGACY-IMPORTED",
                name="Legacy Imported Term",
                status="active",
            )
        )
        db.commit()
    return engine, Session


def small_config(seed: int = 9) -> DemoDataConfig:
    return DemoDataConfig(
        seed=seed,
        student_count=16,
        faculty_count=8,
        room_count=8,
        sections=("A", "B"),
        semesters=8,
        courses_per_semester=4,
    )


def snapshot(Session) -> dict:
    with Session() as db:
        return {
            "term": [
                (row.code, row.name, row.status)
                for row in db.scalars(select(AcademicTerm).order_by(AcademicTerm.id))
            ],
            "students": [
                (row.registration_number, row.current_semester, row.section)
                for row in db.scalars(select(StudentProfile).order_by(StudentProfile.registration_number))
            ],
            "entries": [
                (row.course_code, row.semester, row.section, row.day, row.start_time, row.end_time, row.room)
                for row in db.scalars(select(TimetableEntry).order_by(TimetableEntry.id))
            ],
            "enrollments": [
                (row.user_id, row.course_code, row.section, row.semester)
                for row in db.scalars(select(StudentEnrollment).order_by(StudentEnrollment.id))
            ],
        }


def test_demo_generator_is_deterministic_and_clearly_synthetic():
    engine1, Session1 = create_session()
    engine2, Session2 = create_session()
    try:
        with Session1() as db:
            first = generate_demo_data(db, config=small_config(seed=42))
        with Session2() as db:
            second = generate_demo_data(db, config=small_config(seed=42))

        assert first.to_dict() == second.to_dict()
        assert snapshot(Session1) == snapshot(Session2)
        assert first.students == 16
        assert first.intentional_conflict_pairs == 16
        with Session1() as db:
            emails = list(db.scalars(select(User.email).where(User.email.is_not(None))).all())
            assert emails
            assert all(email.endswith("@synthetic.invalid") for email in emails)
            assert db.scalar(select(func.count(StudentProfile.user_id))) == 16
            sources = set(db.scalars(select(TimetableEntry.source)).all())
            assert sources == {"generated"}
    finally:
        engine1.dispose()
        engine2.dispose()


def test_demo_generator_refuses_non_empty_application_database():
    engine, Session = create_session()
    try:
        with Session() as db:
            db.add(
                User(
                    email="existing@example.edu",
                    full_name="Existing User",
                    password_hash="not-a-real-hash",
                    role="coordinator",
                    is_active=True,
                )
            )
            db.commit()
            with pytest.raises(ValueError, match="refuses a non-empty"):
                assert_demo_database_is_pristine(db)
            with pytest.raises(ValueError, match="refuses a non-empty"):
                generate_demo_data(db, config=small_config())
    finally:
        engine.dispose()


def test_demo_generator_rejects_unsafe_configuration_before_writes():
    engine, Session = create_session()
    try:
        with Session() as db:
            with pytest.raises(ValueError, match="student_count"):
                generate_demo_data(
                    db,
                    config=DemoDataConfig(student_count=1),
                )
            assert db.scalar(select(func.count(User.id))) == 0
            term = db.get(AcademicTerm, 1)
            assert term.code == "LEGACY-IMPORTED"
    finally:
        engine.dispose()


def test_demo_path_guard_blocks_development_and_unmarked_targets(tmp_path: Path):
    project_root = tmp_path / "repo"
    development = project_root / "data" / "unitime_ai.db"
    assert not is_safe_demo_database_path(development, project_root=project_root)
    assert not is_safe_demo_database_path(project_root / "data" / "scratch.db", project_root=project_root)
    assert is_safe_demo_database_path(project_root / "data" / "unitime-demo.db", project_root=project_root)
    assert is_safe_demo_database_path(project_root / "data" / "synthetic.sqlite", project_root=project_root)


def test_demo_benchmark_observes_real_conflicts_and_candidates():
    engine, Session = create_session()
    try:
        with Session() as db:
            summary = generate_demo_data(db, config=small_config(seed=11))
            benchmark = benchmark_demo_resolver(db, term_id=summary.term_id)
        assert benchmark.confirmed_conflict_edges >= 8
        assert benchmark.verified_students == 16
        assert benchmark.enrollment_records > 0
        assert benchmark.affected_students_across_confirmed_edges >= 16
        assert benchmark.candidate_target_entry_id is not None
        assert benchmark.candidates_evaluated > 0
        assert benchmark.runtime_ms >= 0
    finally:
        engine.dispose()


def test_demo_cli_runs_from_repository_root_and_rejects_invalid_config_before_schema(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    target = tmp_path / "integration-demo.db"
    completed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "generate_synthetic_demo.py"),
            "--database",
            str(target),
            "--confirm-synthetic",
            "--students",
            "8",
            "--faculty",
            "8",
            "--rooms",
            "4",
            "--benchmark",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["dataset"]["students"] == 8
    assert payload["benchmark"]["verified_students"] == 8
    assert target.exists() and target.stat().st_size > 0

    rejected = tmp_path / "invalid-demo.db"
    failed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "generate_synthetic_demo.py"),
            "--database",
            str(rejected),
            "--confirm-synthetic",
            "--students",
            "1",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    assert "student_count" in (failed.stderr + failed.stdout)
    assert not rejected.exists()
