from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.database import engine as application_engine
from backend.logging_config import get_logger


logger = get_logger(__name__)


def database_ping(
    db_engine: Engine,
) -> None:
    """
    Verify that a real database connection can be opened
    and a trivial query can be executed.
    """

    with db_engine.connect() as connection:
        connection.execute(
            text("SELECT 1")
        )


def get_migration_revision(
    db_engine: Engine,
) -> str | None:
    """
    Return the current Alembic database revision.

    None means the database is reachable but has not yet
    been stamped/migrated with Alembic.
    """

    inspector = inspect(
        db_engine
    )

    if "alembic_version" not in inspector.get_table_names():
        return None

    with db_engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT version_num "
                "FROM alembic_version"
            )
        ).scalar()


def check_readiness(
    db_engine: Engine = application_engine,
) -> dict[str, Any]:
    """
    Return deployment readiness information.

    Unexpected database failures are converted into a
    controlled RuntimeError so the API can return HTTP 503
    rather than exposing internal database details.
    """

    try:
        database_ping(
            db_engine
        )

        revision = get_migration_revision(
            db_engine
        )

    except Exception as exc:
        logger.exception(
            "Database readiness check failed."
        )

        raise RuntimeError(
            "Service database is not ready."
        ) from exc

    return {
        "status": "ready",
        "database": "connected",
        "migrations": {
            "managed": revision is not None,
            "revision": revision,
        },
    }