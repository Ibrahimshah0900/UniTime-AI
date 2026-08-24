from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

import backend.readiness as readiness


def make_revision_engine(
    revision: str | None,
):
    engine = create_engine(
        "sqlite:///:memory:"
    )

    if revision is not None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO alembic_version "
                    "(version_num) VALUES (:revision)"
                ),
                {
                    "revision": revision,
                },
            )

    return engine


def test_expected_migration_head_is_discoverable():
    revision = (
        readiness.get_expected_migration_revision()
    )

    assert isinstance(
        revision,
        str,
    )
    assert revision


def test_readiness_reports_database_at_head(
    monkeypatch,
):
    engine = make_revision_engine(
        "expected-head"
    )

    monkeypatch.setattr(
        readiness,
        "get_expected_migration_revision",
        lambda: "expected-head",
    )

    result = readiness.check_readiness(
        engine,
        require_migration_head=True,
    )

    assert result["status"] == "ready"
    assert result["migrations"][
        "at_head"
    ] is True
    assert result["migrations"][
        "expected_revision"
    ] == "expected-head"


def test_non_strict_readiness_preserves_legacy_contract(
    monkeypatch,
):
    engine = make_revision_engine(
        "old-head"
    )

    monkeypatch.setattr(
        readiness,
        "get_expected_migration_revision",
        lambda: "new-head",
    )

    result = readiness.check_readiness(
        engine
    )

    assert result == {
        "status": "ready",
        "database": "connected",
        "migrations": {
            "managed": True,
            "revision": "old-head",
        },
    }


def test_strict_readiness_rejects_mismatch(
    monkeypatch,
):
    engine = make_revision_engine(
        "old-head"
    )

    monkeypatch.setattr(
        readiness,
        "get_expected_migration_revision",
        lambda: "new-head",
    )

    with pytest.raises(
        RuntimeError,
        match="not at the application head",
    ):
        readiness.check_readiness(
            engine,
            require_migration_head=True,
        )


def test_strict_readiness_rejects_unmanaged_database(
    monkeypatch,
):
    engine = make_revision_engine(
        None
    )

    monkeypatch.setattr(
        readiness,
        "get_expected_migration_revision",
        lambda: "expected-head",
    )

    with pytest.raises(
        RuntimeError,
        match="not at the application head",
    ):
        readiness.check_readiness(
            engine,
            require_migration_head=True,
        )
