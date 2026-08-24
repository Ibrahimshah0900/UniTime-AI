from __future__ import annotations

from unittest.mock import Mock

from backend.concurrency import TIMETABLE_WRITE_LOCK_ID, acquire_timetable_write_lock


def test_sqlite_relies_on_database_write_serialization():
    session = Mock()
    session.get_bind.return_value.dialect.name = "sqlite"

    acquire_timetable_write_lock(session)

    session.execute.assert_not_called()


def test_postgresql_uses_transaction_scoped_advisory_lock():
    session = Mock()
    session.get_bind.return_value.dialect.name = "postgresql"

    acquire_timetable_write_lock(session)

    statement, parameters = session.execute.call_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert parameters == {"lock_id": TIMETABLE_WRITE_LOCK_ID}
