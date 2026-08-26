from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.demo_data import (
    DemoDataConfig,
    benchmark_demo_resolver,
    generate_demo_data,
    is_safe_demo_database_path,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an isolated, deterministic UniTime-AI synthetic demo database."
    )
    parser.add_argument("--database", required=True, help="New SQLite demo database path.")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--students", type=int, default=320)
    parser.add_argument("--faculty", type=int, default=16)
    parser.add_argument("--rooms", type=int, default=16)
    parser.add_argument(
        "--confirm-synthetic",
        action="store_true",
        help="Required acknowledgement that this target is disposable synthetic data.",
    )
    parser.add_argument("--benchmark", action="store_true")
    return parser.parse_args()


def _prepare_schema(target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        raise ValueError("Refusing to migrate over a non-empty demo database file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{target.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["APP_ENV"] = "development"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )


def main() -> int:
    args = _parse_args()
    if not args.confirm_synthetic:
        raise SystemExit(
            "Refusing generation without --confirm-synthetic. No data was written."
        )

    target = Path(args.database)
    if not is_safe_demo_database_path(target, project_root=PROJECT_ROOT):
        raise SystemExit(
            "Refusing target. Use an isolated SQLite file whose name contains "
            "'demo' or 'synthetic'; data/unitime_ai.db is never allowed."
        )
    if target.exists() and target.stat().st_size > 0:
        raise SystemExit("Refusing an existing non-empty target database.")

    config = DemoDataConfig(
        seed=args.seed,
        student_count=args.students,
        faculty_count=args.faculty,
        room_count=args.rooms,
    )
    config.validate()

    try:
        _prepare_schema(target)
        engine = create_engine(
            f"sqlite:///{target.resolve().as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with Session() as db:
            summary = generate_demo_data(db, config=config)
            result = {"dataset": summary.to_dict()}
            if args.benchmark:
                result["benchmark"] = benchmark_demo_resolver(
                    db, term_id=summary.term_id
                ).to_dict()
        engine.dispose()
    except Exception:
        # A failed generation target is disposable by definition, but do not
        # silently delete it; the caller can inspect and remove it explicitly.
        raise

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
