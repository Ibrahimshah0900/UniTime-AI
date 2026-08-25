from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "36bb9325c02a"
HISTORY_HEAD = "a875c1fd272c"


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


def seed_legacy_change(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        entry = connection.execute(
            """
            INSERT INTO timetable_entries (
                term_id, entry_kind, course_code, course_name, semester,
                section, faculty, room, day, start_time, end_time,
                class_type, raw_text, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "course",
                "AI-301",
                "Artificial Intelligence",
                "Fall 2026",
                "A",
                "Dr Ada",
                "R-101",
                "Monday",
                "10:00",
                "11:00",
                "lecture",
                None,
                "manual",
            ),
        )
        change = connection.execute(
            """
            INSERT INTO student_schedule_changes (
                term_id, entry_id, group_id, change_type,
                old_day, old_start_time, old_end_time,
                new_day, new_start_time, new_end_time,
                score, reasons_json, risk_cost_before, risk_cost_after,
                total_risks_before, total_risks_after, undone, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                int(entry.lastrowid),
                7,
                "student_conflict_move",
                "Monday",
                "10:00",
                "11:00",
                "Tuesday",
                "10:00",
                "11:00",
                80.0,
                "[]",
                100,
                0,
                1,
                0,
                0,
                "2026-01-01 00:00:00",
            ),
        )
        return int(change.lastrowid)


def test_report_resolution_history_migration_preserves_rows_and_round_trips(tmp_path):
    database_path = tmp_path / "report-resolution-history.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    legacy_change_id = seed_legacy_change(database_path)

    run_alembic(database_path, "upgrade", HISTORY_HEAD)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row for row in connection.execute(
                "PRAGMA table_info(student_schedule_changes)"
            )
        }
        legacy = connection.execute(
            """
            SELECT group_id, report_id, actor_user_id, candidate_id,
                   safety_status, report_resolution_note
            FROM student_schedule_changes WHERE id = ?
            """,
            (legacy_change_id,),
        ).fetchone()
        inserted = connection.execute(
            """
            INSERT INTO student_schedule_changes (
                term_id, entry_id, group_id, report_id, actor_user_id,
                candidate_id, safety_status, report_resolution_note,
                change_type, old_day, old_start_time, old_end_time,
                new_day, new_start_time, new_end_time, score, reasons_json,
                risk_cost_before, risk_cost_after, total_risks_before,
                total_risks_after, undone, created_at
            )
            SELECT term_id, entry_id, NULL, NULL, NULL, ?, ?, ?, ?,
                   old_day, old_start_time, old_end_time,
                   new_day, new_start_time, new_end_time, score, reasons_json,
                   risk_cost_before, risk_cost_after, total_risks_before,
                   total_risks_after, undone, created_at
            FROM student_schedule_changes WHERE id = ?
            """,
            (
                "0123456789abcdef01234567",
                "CONDITIONALLY_SAFE",
                "Coordinator confirmed limitations.",
                "clash_report_resolution",
                legacy_change_id,
            ),
        )
        inserted_id = int(inserted.lastrowid)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE student_schedule_changes SET safety_status = ? WHERE id = ?",
                ("UNSAFE_BUT_ACCEPTED", inserted_id),
            )

    assert columns["group_id"][3] == 0
    assert {
        "report_id",
        "actor_user_id",
        "candidate_id",
        "safety_status",
        "report_resolution_note",
    }.issubset(columns)
    assert legacy == (7, None, None, None, None, None)

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        downgraded_columns = {
            row[1]: row for row in connection.execute(
                "PRAGMA table_info(student_schedule_changes)"
            )
        }
        groups = connection.execute(
            "SELECT group_id FROM student_schedule_changes ORDER BY id"
        ).fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert "report_id" not in downgraded_columns
    assert downgraded_columns["group_id"][3] == 1
    assert groups == [(7,), (0,)]
    assert revision == (PREVIOUS_HEAD,)

    run_alembic(database_path, "upgrade", HISTORY_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM student_schedule_changes"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HISTORY_HEAD,)
