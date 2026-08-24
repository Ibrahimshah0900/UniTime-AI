from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from backend.readiness import (
    check_readiness,
    database_ping,
    get_migration_revision,
)


def create_memory_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
    )


def test_database_ping_succeeds():
    engine = create_memory_engine()

    database_ping(engine)

    engine.dispose()


def test_unversioned_database_is_still_reachable():
    engine = create_memory_engine()

    result = check_readiness(engine)

    assert result["status"] == "ready"
    assert result["database"] == "connected"

    assert result["migrations"] == {
        "managed": False,
        "revision": None,
    }

    engine.dispose()


def test_alembic_revision_is_detected():
    engine = create_memory_engine()

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            )
        )

        connection.execute(
            text(
                "INSERT INTO alembic_version "
                "(version_num) "
                "VALUES ('test_revision_123')"
            )
        )

    revision = get_migration_revision(engine)

    assert revision == "test_revision_123"

    result = check_readiness(engine)

    assert result["migrations"] == {
        "managed": True,
        "revision": "test_revision_123",
    }

    engine.dispose()


def test_database_failure_becomes_safe_runtime_error():
    class BrokenEngine:
        def connect(self):
            raise RuntimeError(
                "secret database connection failure"
            )

    with pytest.raises(
        RuntimeError,
        match="Service database is not ready",
    ):
        check_readiness(
            BrokenEngine()
        )