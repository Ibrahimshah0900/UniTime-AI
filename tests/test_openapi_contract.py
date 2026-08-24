from __future__ import annotations

import json
from pathlib import Path

from backend.app import app


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def test_committed_openapi_contract_matches_application():
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed == app.openapi()


def test_api_contract_version_is_stable_for_frontend_handoff():
    assert app.version == "0.6.0"
    assert len(app.openapi()["paths"]) == 53
