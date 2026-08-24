from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine import engine_from_config

from backend.database import Base, DATABASE_URL

# Import every module that declares SQLAlchemy models.
# These imports register the tables with Base.metadata.
import backend.models  # noqa: F401
import backend.student_resolution_applier  # noqa: F401
import backend.optimizer_execution_history  # noqa: F401


config = context.config


if config.config_file_name is not None:
    fileConfig(
        config.config_file_name
    )


# Alembic autogenerate will compare migrations against
# the same metadata used by the FastAPI application.
target_metadata = Base.metadata


# Always use the application's DATABASE_URL rather than
# keeping a second hardcoded database configuration inside
# alembic.ini.
config.set_main_option(
    "sqlalchemy.url",
    DATABASE_URL.replace("%", "%%"),
)


def run_migrations_offline() -> None:
    """
    Run migrations without creating a live DB connection.
    """

    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations using a live database connection.
    """

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        configure_context(
            connection
        )

        with context.begin_transaction():
            context.run_migrations()


def configure_context(
    connection: Connection,
) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()