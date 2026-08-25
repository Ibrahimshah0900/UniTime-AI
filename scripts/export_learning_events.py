from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal  # noqa: E402
from backend.learning_event_export import (  # noqa: E402
    domain_learning_events_csv,
    export_domain_learning_events,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PII-guarded UniTime-AI domain learning events."
    )
    parser.add_argument("output", type=Path, help="Output .json or .csv path.")
    parser.add_argument("--term-id", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.output.suffix.lower() not in {".json", ".csv"}:
        raise SystemExit("Output path must end in .json or .csv.")
    with SessionLocal() as db:
        dataset = export_domain_learning_events(db, term_id=arguments.term_id)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    if arguments.output.suffix.lower() == ".csv":
        content = domain_learning_events_csv(dataset)
    else:
        content = json.dumps(dataset, indent=2, sort_keys=True) + "\n"
    arguments.output.write_text(content, encoding="utf-8")
    print(f"Exported {dataset['event_count']} event(s) to {arguments.output}")


if __name__ == "__main__":
    main()
