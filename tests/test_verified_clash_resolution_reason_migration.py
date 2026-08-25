from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "174e0a995fe0"
RESOLUTION_REASON_HEAD = "b8438f7b555a"


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


def seed_existing_resolved_report(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        user = connection.execute(
            """
            INSERT INTO users (
                email, full_name, password_hash, token_version,
                must_change_password, role, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "resolved.student@example.edu",
                "Resolved Student",
                "hash",
                0,
                0,
                "student",
                1,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        report = connection.execute(
            """
            INSERT INTO student_clash_reports (
                term_id, student_user_id,
                student_registration_number_snapshot,
                student_name_snapshot, student_email_snapshot,
                student_department_snapshot, student_program_snapshot,
                student_batch_snapshot, student_semester_snapshot,
                student_section_snapshot, conflict_fingerprint,
                status, notes, evidence_reference, duplicate_of_report_id,
                resolution_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                int(user.lastrowid),
                "FA23-BAI-042",
                "Resolved Student",
                "resolved.student@example.edu",
                "Computer Science",
                "BS Artificial Intelligence",
                "Fall 2023",
                6,
                "A",
                "a" * 64,
                "resolved",
                "Legacy resolved report",
                None,
                None,
                "Resolved before structured reasons existed.",
                "2026-01-02 00:00:00",
                "2026-01-02 00:00:00",
            ),
        )
        return int(report.lastrowid)


def test_verified_resolution_reason_migration_preserves_rows_and_round_trips(
    tmp_path,
):
    database_path = tmp_path / "verified-resolution-reason.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    report_id = seed_existing_resolved_report(database_path)

    run_alembic(database_path, "upgrade", RESOLUTION_REASON_HEAD)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row
            for row in connection.execute(
                "PRAGMA table_info(student_clash_reports)"
            )
        }
        preserved = connection.execute(
            """
            SELECT status, resolution_note, resolution_reason
            FROM student_clash_reports WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE student_clash_reports
            SET resolution_reason = 'timetable_changed'
            WHERE id = ?
            """,
            (report_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE student_clash_reports
                SET resolution_reason = 'unverified_claim'
                WHERE id = ?
                """,
                (report_id,),
            )

    assert columns["resolution_reason"][3] == 0
    assert preserved == (
        "resolved",
        "Resolved before structured reasons existed.",
        None,
    )

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        downgraded_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(student_clash_reports)"
            )
        }
        assert "resolution_reason" not in downgraded_columns
        assert connection.execute(
            "SELECT status, resolution_note FROM student_clash_reports WHERE id = ?",
            (report_id,),
        ).fetchone() == (
            "resolved",
            "Resolved before structured reasons existed.",
        )

    run_alembic(database_path, "upgrade", RESOLUTION_REASON_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT resolution_reason FROM student_clash_reports WHERE id = ?",
            (report_id,),
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RESOLUTION_REASON_HEAD,)
