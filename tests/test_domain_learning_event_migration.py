from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "b8438f7b555a"
LEARNING_EVENT_HEAD = "738057d5ac81"


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


def test_domain_learning_event_migration_constraints_and_round_trip(tmp_path):
    database_path = tmp_path / "domain-learning-events.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    run_alembic(database_path, "upgrade", LEARNING_EVENT_HEAD)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(learning_events)")
        }
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(learning_events)")
        }
        connection.execute(
            """
            INSERT INTO learning_events (
                term_id, event_type, subject_key, entity_type, entity_key,
                actor_role, source, outcome_label, context_schema_version,
                context_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "student_enrolled",
                "a" * 64,
                "enrollment",
                "b" * 64,
                "student",
                "backend",
                "no_conflict",
                "1.0",
                "{}",
                "2026-08-25 10:00:00",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO learning_events (
                    event_type, entity_type, entity_key, actor_role, source,
                    context_schema_version, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "model_trained",
                    "model",
                    "c" * 64,
                    "system",
                    "backend",
                    "1.0",
                    "{}",
                    "2026-08-25 10:00:00",
                ),
            )

    assert {
        "id",
        "term_id",
        "event_type",
        "subject_key",
        "entity_type",
        "entity_key",
        "actor_role",
        "source",
        "outcome_label",
        "context_schema_version",
        "context_json",
        "created_at",
    } == columns
    assert {
        "ix_learning_events_entity_key",
        "ix_learning_events_term_id",
        "ix_learning_events_type_created",
    }.issubset(indexes)

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert "learning_events" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    run_alembic(database_path, "upgrade", LEARNING_EVENT_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (LEARNING_EVENT_HEAD,)
