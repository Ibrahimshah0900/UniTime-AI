from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


# One transaction-scoped PostgreSQL advisory lock serializes timetable writers
# across API workers. SQLite already serializes writes at the database level.
TIMETABLE_WRITE_LOCK_ID = 2_408_250_001


def acquire_timetable_write_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": TIMETABLE_WRITE_LOCK_ID},
    )
