from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from backend.candidate_ranker import CandidateFeatures
from backend.experimental_ranker import (
    CandidateRankerRuntimeError,
    ExperimentalCatBoostRanker,
)


ARTIFACT_DIR = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "ai_ranker"
    / "research_v1"
)


def features(status: str = "SAFE") -> CandidateFeatures:
    return CandidateFeatures(
        safety_status=status,
        duration_minutes=60,
        affected_students=12,
        confirmed_conflicts_removed=1,
        inferred_conflicts_removed=0,
        structural_clashes_removed=1,
        conflict_groups_removed=1,
        weighted_risk_reduction=100,
        day_distance=1,
        time_shift_minutes=60,
        late_slot=False,
        missing_metadata_count=0 if status == "SAFE" else 1,
    )


def test_frozen_research_v1_bundle_loads_and_returns_bounded_signal():
    ranker = ExperimentalCatBoostRanker(ARTIFACT_DIR)

    safe = ranker.rank(features("SAFE"))
    conditional = ranker.rank(features("CONDITIONALLY_SAFE"))

    assert 0 <= safe.score <= 100
    assert 0 <= conditional.score <= 100
    assert safe.components[0].signal == "catboost_research_v1"
    assert "not a probability" in safe.components[0].explanation


def test_research_v1_refuses_insufficient_data_before_inference():
    ranker = ExperimentalCatBoostRanker(ARTIFACT_DIR)

    with pytest.raises(CandidateRankerRuntimeError, match="only accepts SAFE"):
        ranker.rank(features("INSUFFICIENT_DATA"))


def test_schema_mismatch_is_a_safe_runtime_failure(tmp_path: Path):
    copied = tmp_path / "ranker"
    shutil.copytree(ARTIFACT_DIR, copied)
    contract_path = copied / "feature_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["version"] = "999"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    ranker = ExperimentalCatBoostRanker(copied)
    with pytest.raises(CandidateRankerRuntimeError, match="feature contract version"):
        ranker.rank(features("SAFE"))


def test_missing_model_is_a_safe_runtime_failure(tmp_path: Path):
    copied = tmp_path / "ranker"
    shutil.copytree(ARTIFACT_DIR, copied)
    (copied / "model.cbm").unlink()

    ranker = ExperimentalCatBoostRanker(copied)
    with pytest.raises(CandidateRankerRuntimeError, match="artifact is missing"):
        ranker.rank(features("SAFE"))
