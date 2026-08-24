from __future__ import annotations

from collections import Counter
from importlib import import_module

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


app_module = import_module(
    "backend.app"
)
app = app_module.app


CORE_ROUTES = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/timetable"),
    ("POST", "/timetable/import"),
    ("GET", "/clashes"),
    ("GET", "/clashes/student-risk"),
    ("GET", "/optimizer/global"),
    ("GET", "/optimizer/plan"),
    ("POST", "/optimizer/plan/apply"),
    ("GET", "/optimizer/executions"),
}


def route_pairs() -> list[tuple[str, str]]:
    pairs: list[
        tuple[str, str]
    ] = []

    for route in app.routes:
        if not isinstance(
            route,
            APIRoute,
        ):
            continue

        for method in route.methods:
            if method in {
                "HEAD",
                "OPTIONS",
            }:
                continue

            pairs.append(
                (
                    method,
                    route.path,
                )
            )

    return pairs


def test_core_api_routes_are_registered():
    assert CORE_ROUTES.issubset(
        set(route_pairs())
    )


def test_api_has_no_duplicate_method_path_pairs():
    counts = Counter(
        route_pairs()
    )

    duplicates = {
        pair: count
        for pair, count in counts.items()
        if count > 1
    }

    assert duplicates == {}


def test_openapi_schema_builds_with_core_paths():
    schema = app.openapi()

    assert schema["openapi"]
    assert "/timetable" in schema[
        "paths"
    ]
    assert "/optimizer/global" in schema[
        "paths"
    ]
    assert "/optimizer/plan" in schema[
        "paths"
    ]


def test_ready_endpoint_requires_migration_head(
    monkeypatch,
):
    captured: dict[
        str,
        bool,
    ] = {}

    def fake_check_readiness(
        *,
        require_migration_head: bool = False,
    ):
        captured[
            "require_migration_head"
        ] = require_migration_head

        return {
            "status": "ready",
            "database": "connected",
            "migrations": {
                "managed": True,
                "revision": "head",
                "expected_revision": "head",
                "at_head": True,
            },
        }

    monkeypatch.setattr(
        app_module,
        "check_readiness",
        fake_check_readiness,
    )

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ready"
    )

    assert response.status_code == 200
    assert captured[
        "require_migration_head"
    ] is True
