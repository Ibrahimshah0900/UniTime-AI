from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "8ff39f7b22e6"
IDENTITY_HEAD = "5989aedcfe45"


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


def seed_legacy_student(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (
                email, full_name, password_hash, token_version, role,
                is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy.student@example.edu",
                "Legacy Student",
                "legacy-hash",
                0,
                "student",
                1,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        return int(cursor.lastrowid)


def test_student_identity_migration_backfills_without_false_verification_and_round_trips(
    tmp_path,
):
    database_path = tmp_path / "student-identity-migration.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    legacy_user_id = seed_legacy_student(database_path)

    run_alembic(database_path, "upgrade", IDENTITY_HEAD)
    with sqlite3.connect(database_path) as connection:
        profile = connection.execute(
            """
            SELECT registration_number, department, is_verified,
                   onboarding_completed
            FROM student_profiles WHERE user_id = ?
            """,
            (legacy_user_id,),
        ).fetchone()
        user = connection.execute(
            "SELECT email, must_change_password FROM users WHERE id = ?",
            (legacy_user_id,),
        ).fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        connection.execute(
            """
            INSERT INTO users (
                email, full_name, password_hash, token_version,
                must_change_password, role, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "Registration Only Student",
                "temporary-hash",
                0,
                1,
                "student",
                1,
                "2026-01-02 00:00:00",
                "2026-01-02 00:00:00",
            ),
        )

    assert profile == (
        f"LEGACY-{legacy_user_id:08d}",
        "Unspecified",
        0,
        1,
    )
    assert user == ("legacy.student@example.edu", 0)
    assert revision == (IDENTITY_HEAD,)

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(users)")
        }
        emails = connection.execute("SELECT email FROM users ORDER BY id").fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert "must_change_password" not in columns
    assert columns["email"][3] == 1
    assert emails[0] == ("legacy.student@example.edu",)
    assert emails[1][0].endswith("@invalid.local")
    assert revision == (PREVIOUS_HEAD,)

    run_alembic(database_path, "upgrade", IDENTITY_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM student_profiles"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (IDENTITY_HEAD,)

