from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "a875c1fd272c"
LEARNING_HEAD = "174e0a995fe0"


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


def test_resolution_learning_event_migration_round_trips(tmp_path):
    database_path = tmp_path / "resolution-learning-events.db"
    run_alembic(database_path, "upgrade", PREVIOUS_HEAD)
    run_alembic(database_path, "upgrade", LEARNING_HEAD)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(resolution_learning_events)"
            )
        }
        indexes = {
            row[1] for row in connection.execute(
                "PRAGMA index_list(resolution_learning_events)"
            )
        }
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("resolution_learning_events",),
        ).fetchone()[0]
    assert {
        "term_id",
        "report_id",
        "change_id",
        "candidate_id",
        "event_type",
        "outcome_label",
        "ranker_id",
        "ranker_version",
        "feature_schema_version",
        "safety_status",
        "features_json",
        "rank_score",
    }.issubset(columns)
    assert "ix_resolution_learning_events_change_id" in indexes
    assert "ck_resolution_learning_events_event_type" in table_sql
    assert "ck_resolution_learning_events_safety_status" in table_sql

    run_alembic(database_path, "downgrade", PREVIOUS_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("resolution_learning_events",),
        ).fetchone() is None
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (PREVIOUS_HEAD,)

    run_alembic(database_path, "upgrade", LEARNING_HEAD)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (LEARNING_HEAD,)
