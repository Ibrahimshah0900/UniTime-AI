from __future__ import annotations

import json
from pathlib import Path

from backend.app import app


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def test_committed_openapi_contract_matches_application():
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed == app.openapi()


def test_api_contract_version_is_stable_for_frontend_handoff():
    assert app.version == "0.16.0"
    assert len(app.openapi()["paths"]) == 71
    assert "/faculty/free-slots" in app.openapi()["paths"]
    assert "/clash-reports/clusters" in app.openapi()["paths"]
    assert "/student/enrollments/validate" in app.openapi()["paths"]
    assert "/data-quality" in app.openapi()["paths"]
    assert "/resolver-analytics" in app.openapi()["paths"]


def test_successful_json_operations_publish_response_schemas():
    schema = app.openapi()
    untyped_operations: list[tuple[str, str]] = []

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses = operation.get("responses", {})
            success = responses.get("200") or responses.get("201")
            if success is None:
                continue
            response_schema = (
                success.get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if response_schema == {}:
                untyped_operations.append((method.upper(), path))

    assert untyped_operations == []
