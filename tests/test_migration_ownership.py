from __future__ import annotations

import re
from pathlib import Path


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "backend"
)


def runtime_backend_sources() -> list[Path]:
    return sorted(
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_runtime_backend_never_calls_create_all():
    offenders: list[str] = []

    for path in runtime_backend_sources():
        source = path.read_text(
            encoding="utf-8"
        )

        if re.search(
            r"\bcreate_all\s*\(",
            source,
        ):
            offenders.append(
                str(
                    path.relative_to(
                        BACKEND_ROOT.parent
                    )
                )
            )

    assert offenders == [], (
        "Database schema creation must be owned "
        "by Alembic, not runtime application code: "
        f"{offenders}"
    )


def test_execution_history_runtime_schema_helper_is_removed():
    offenders: list[str] = []

    for path in runtime_backend_sources():
        source = path.read_text(
            encoding="utf-8"
        )

        if (
            "ensure_execution_history_tables"
            in source
        ):
            offenders.append(
                str(
                    path.relative_to(
                        BACKEND_ROOT.parent
                    )
                )
            )

    assert offenders == [], (
        "Runtime execution-history schema helper "
        f"must remain removed: {offenders}"
    )
