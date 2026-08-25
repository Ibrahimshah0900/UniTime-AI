from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "5989aedcfe45"
SNAPSHOT_HEAD = "36bb9325c02a"


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


def seed_report(database_path: Path) -> tuple[int, int]:
    with sqlite3.connect(database_path) as connection:
        user_cursor = connection.execute(
            """
            INSERT INTO users (
                email, full_name, password_hash, token_version,
                must_change_password, role, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snapshot.student@example.edu",
                "Snapshot Student",
                "hash",
                0,
                0,
                "student",
                1,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        user_id = int(user_cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO student_profiles (
                user_id, registration_number, department, program, batch,
                current_semester, section, academic_status, is_verified,
                preferred_name, onboarding_completed, created_by_user_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                "FA23-BAI-042",
                "Computer Science",
                "BS Artificial Intelligence",
                "Fall 2023",
                6,
                "A",
                "active",
                1,
                None,
                1,
                None,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        report_cursor = connection.execute(
            """
            INSERT INTO student_clash_reports (
                term_id, student_user_id, status, notes, evidence_reference,
                duplicate_of_report_id, resolution_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                user_id,
                "submitted",
                "Legacy report",
                None,
                None,
                None,
                "2026-01-02 00:00:00",
                "2026-01-02 00:00:00",
            ),
        )
        return user_id, int(report_cursor.lastrowid)


def test_report_snapshot_migration_preserves_and_freezes_existing_identity(tmp_path):
    database_path = tmp_path / "report-snapshot-migration.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    user_id, report_id = seed_report(database_path)

    run_alembic(database_path, "upgrade", SNAPSHOT_HEAD)
    with sqlite3.connect(database_path) as connection:
        snapshot = connection.execute(
            """
            SELECT student_registration_number_snapshot,
                   student_name_snapshot, student_email_snapshot,
                   student_department_snapshot, student_program_snapshot,
                   student_batch_snapshot, student_semester_snapshot,
                   student_section_snapshot, conflict_fingerprint
            FROM student_clash_reports WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        connection.execute(
            "UPDATE users SET full_name = ? WHERE id = ?",
            ("Changed Name", user_id),
        )
        connection.execute(
            "UPDATE student_profiles SET program = ? WHERE user_id = ?",
            ("Changed Program", user_id),
        )
        unchanged = connection.execute(
            "SELECT student_name_snapshot, student_program_snapshot FROM student_clash_reports WHERE id = ?",
            (report_id,),
        ).fetchone()

    assert snapshot[:8] == (
        "FA23-BAI-042",
        "Snapshot Student",
        "snapshot.student@example.edu",
        "Computer Science",
        "BS Artificial Intelligence",
        "Fall 2023",
        6,
        "A",
    )
    assert len(snapshot[8]) == 64
    assert unchanged == ("Snapshot Student", "BS Artificial Intelligence")

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(student_clash_reports)")
        }
        assert "conflict_fingerprint" not in columns
        assert connection.execute(
            "SELECT notes FROM student_clash_reports WHERE id = ?",
            (report_id,),
        ).fetchone() == ("Legacy report",)

    run_alembic(database_path, "upgrade", SNAPSHOT_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (SNAPSHOT_HEAD,)
        assert connection.execute(
            "SELECT COUNT(*) FROM student_clash_reports"
        ).fetchone() == (1,)

