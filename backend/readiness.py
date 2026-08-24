from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.database import engine as application_engine
from backend.logging_config import get_logger


logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG_PATH = PROJECT_ROOT / "alembic.ini"


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


def get_expected_migration_revision() -> str:
    """
    Return the single Alembic head expected by this
    application checkout.
    """

    config = Config(
        str(ALEMBIC_CONFIG_PATH)
    )
    script = ScriptDirectory.from_config(
        config
    )
    heads = script.get_heads()

    if len(heads) != 1:
        raise RuntimeError(
            "Application migration history must have "
            "exactly one head."
        )

    return heads[0]


def check_readiness(
    db_engine: Engine = application_engine,
    *,
    require_migration_head: bool = False,
) -> dict[str, Any]:
    """
    Return deployment readiness information.

    The default mode preserves the original readiness
    response contract. Strict mode additionally requires
    the database revision to equal the Alembic head shipped
    with the application.
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

    if not require_migration_head:
        return {
            "status": "ready",
            "database": "connected",
            "migrations": {
                "managed": revision is not None,
                "revision": revision,
            },
        }

    try:
        expected_revision = (
            get_expected_migration_revision()
        )

    except Exception as exc:
        logger.exception(
            "Migration metadata readiness check failed."
        )

        raise RuntimeError(
            "Service migration metadata is not ready."
        ) from exc

    at_head = (
        revision == expected_revision
    )

    if not at_head:
        logger.error(
            "Database migration revision is not at "
            "application head; current=%s expected=%s",
            revision,
            expected_revision,
        )

        raise RuntimeError(
            "Service database migrations are not at "
            "the application head."
        )

    return {
        "status": "ready",
        "database": "connected",
        "migrations": {
            "managed": True,
            "revision": revision,
            "expected_revision": expected_revision,
            "at_head": True,
        },
    }
