from __future__ import annotations

from unittest.mock import Mock

import backend.multi_step_plan_applier as multi_step_plan_applier
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

def test_multi_step_plan_reacquires_lock_after_internal_commits(monkeypatch):
    db = Mock()
    snapshot = {
        "student_risk_cost": 10,
        "student_risks": {"total": 1},
        "student_groups": 1,
        "clashes": {"total": 0},
    }
    move = {
        "entry_id": 7,
        "room_status": "available",
    }
    optimizer_results = iter(
        [
            {"ranked_moves": [move]},
            {"ranked_moves": []},
        ]
    )
    lock_commit_counts: list[int] = []

    monkeypatch.setattr(
        multi_step_plan_applier,
        "get_all_entries",
        lambda _db: [],
    )
    monkeypatch.setattr(
        multi_step_plan_applier,
        "build_timetable_snapshot",
        lambda _entries: snapshot,
    )
    monkeypatch.setattr(
        multi_step_plan_applier,
        "create_execution",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        multi_step_plan_applier,
        "optimize_timetable_globally",
        lambda *_args, **_kwargs: next(optimizer_results),
    )
    monkeypatch.setattr(
        multi_step_plan_applier,
        "acquire_timetable_write_lock",
        lambda _db: lock_commit_counts.append(db.commit.call_count),
    )

    def fake_apply_one_live_step(session, **_kwargs):
        session.commit()
        return {"entry_id": move["entry_id"]}

    monkeypatch.setattr(
        multi_step_plan_applier,
        "apply_one_live_step",
        fake_apply_one_live_step,
    )

    result = multi_step_plan_applier.apply_multi_step_optimization_plan(
        db,
        max_steps=2,
    )

    assert result["status"] == "partial"
    assert result["applied_steps"] == 1
    assert lock_commit_counts == [1, 2]
    db.rollback.assert_not_called()
