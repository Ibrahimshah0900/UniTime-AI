from __future__ import annotations

import argparse
import json
import signal
from threading import Event
from typing import Any

from backend.database import SessionLocal
from backend.logging_config import configure_logging, get_logger
from backend.notification_service import process_due_notifications


logger = get_logger(__name__)


def run_once() -> dict[str, Any]:
    """Process all due notification jobs in one database transaction cycle."""

    with SessionLocal() as db:
        return process_due_notifications(db)


def run_continuously(interval_seconds: int, stop_event: Event) -> None:
    """Run the idempotent processor until the process receives a stop signal."""

    while not stop_event.is_set():
        try:
            result = run_once()
            logger.info("notification_jobs_processed", extra={"result": result})
        except Exception:
            logger.exception("notification_jobs_failed")
        stop_event.wait(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process UniTime-AI reminder and daily-summary notification jobs."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process due jobs once and exit (recommended for platform cron jobs).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Continuous worker interval; must be at least 30 seconds.",
    )
    args = parser.parse_args()

    configure_logging()
    if args.once:
        print(json.dumps(run_once(), sort_keys=True))
        return
    if args.interval_seconds < 30:
        raise SystemExit("--interval-seconds must be at least 30.")

    stop_event = Event()

    def request_stop(*_: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run_continuously(args.interval_seconds, stop_event)


if __name__ == "__main__":
    main()
