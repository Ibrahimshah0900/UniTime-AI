from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal  # noqa: E402
from backend.learning_dataset_service import (  # noqa: E402
    build_ranker_dataset,
    ranker_dataset_to_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PII-free timetable resolution ranking examples.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--term-id", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    if arguments.term_id is not None and arguments.term_id < 1:
        raise SystemExit("--term-id must be a positive integer.")
    with SessionLocal() as db:
        dataset = build_ranker_dataset(db, term_id=arguments.term_id)
    content = (
        json.dumps(dataset, indent=2, sort_keys=True) + "\n"
        if arguments.format == "json"
        else ranker_dataset_to_csv(dataset)
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(content, encoding="utf-8", newline="")
    print(
        f"Exported {dataset['total_examples']} reviewed example(s) "
        f"to {arguments.output}."
    )


if __name__ == "__main__":
    main()
