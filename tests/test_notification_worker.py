from __future__ import annotations

from backend import notification_worker


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def test_notification_worker_runs_processor_with_managed_session(monkeypatch):
    session = FakeSession()
    expected = {
        "reminders_created": 2,
        "summaries_created": 1,
        "processed_users": 4,
        "timezone": "Asia/Karachi",
    }
    monkeypatch.setattr(notification_worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        notification_worker,
        "process_due_notifications",
        lambda db: expected if db is session else None,
    )

    assert notification_worker.run_once() == expected
