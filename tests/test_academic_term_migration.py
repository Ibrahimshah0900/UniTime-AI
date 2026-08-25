from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "ee8c90bdac09"
TERM_HEAD = "8ff39f7b22e6"


def run_alembic(database_path: Path, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def seed_legacy_timetable_row(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO timetable_entries (
                entry_kind, course_code, course_name, semester, section,
                faculty, room, day, start_time, end_time, class_type,
                raw_text, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "course",
                "LEG-101",
                "Legacy Course",
                None,
                "A",
                "Legacy Faculty",
                "R-1",
                "Monday",
                "09:00",
                "10:00",
                "lecture",
                None,
                "manual",
            ),
        )


def assert_upgraded_state(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        term = connection.execute(
            "SELECT id, code, status FROM academic_terms"
        ).fetchone()
        entry = connection.execute(
            "SELECT course_code, term_id FROM timetable_entries"
        ).fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert term == (1, "LEGACY-IMPORTED", "active")
    assert entry == ("LEG-101", 1)
    assert revision == (TERM_HEAD,)


def test_academic_term_migration_preserves_legacy_rows_and_round_trips(tmp_path):
    database_path = tmp_path / "term-migration.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    seed_legacy_timetable_row(database_path)

    run_alembic(database_path, "upgrade", TERM_HEAD)
    assert_upgraded_state(database_path)

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT course_code FROM timetable_entries"
        ).fetchone() == ("LEG-101",)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (PREVIOUS_HEAD,)

    run_alembic(database_path, "upgrade", TERM_HEAD)
    assert_upgraded_state(database_path)
