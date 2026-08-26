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
    build_recommendation_choice_dataset,
    recommendation_choice_dataset_to_csv,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PII-free observed recommendation-choice ranking groups."
    )
    parser.add_argument("output", type=Path, help="Output .json or .csv path.")
    parser.add_argument("--term-id", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.output.suffix.lower() not in {".json", ".csv"}:
        raise SystemExit("Output path must end in .json or .csv.")
    with SessionLocal() as db:
        dataset = build_recommendation_choice_dataset(db, term_id=arguments.term_id)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    if arguments.output.suffix.lower() == ".csv":
        content = recommendation_choice_dataset_to_csv(dataset)
    else:
        content = json.dumps(dataset, indent=2, sort_keys=True) + "\n"
    arguments.output.write_text(content, encoding="utf-8")
    print(
        "Exported "
        f"{dataset['decision_group_count']} decision group(s) / "
        f"{dataset['candidate_row_count']} candidate row(s) to {arguments.output}"
    )


if __name__ == "__main__":
    main()
