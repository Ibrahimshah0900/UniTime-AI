from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from backend.candidate_ranker import (
    FEATURE_SCHEMA_VERSION,
    CandidateFeatures,
    RankerOutput,
    RankerScoreComponent,
)


DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "ai_ranker" / "research_v1"
EXPECTED_MODEL_VERSION = "research-v1"
EXPECTED_MODEL_STATUS = "EXPERIMENTAL_SYNTHETIC"
EXPECTED_FEATURES = (
    "duration_minutes",
    "affected_students",
    "confirmed_conflicts_removed",
    "inferred_conflicts_removed",
    "structural_clashes_removed",
    "conflict_groups_removed",
    "weighted_risk_reduction",
    "day_distance",
    "time_shift_minutes",
    "missing_metadata_count",
    "late_slot",
    "is_conditionally_safe",
)
ELIGIBLE_STATUSES = {"SAFE", "CONDITIONALLY_SAFE"}


class CandidateRankerRuntimeError(RuntimeError):
    """Expected operational failure that permits deterministic fallback."""


class ExperimentalCatBoostRanker:
    """Frozen synthetic CatBoost research ranker for already-safe candidates only."""

    ranker_id = "catboost_research_v1"
    ranker_version = EXPECTED_MODEL_VERSION

    def __init__(self, artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._model: Any | None = None
        self._unavailable_reason: str | None = None

    def _fail(self, message: str, *, cause: Exception | None = None) -> None:
        self._unavailable_reason = message
        if cause is None:
            raise CandidateRankerRuntimeError(message)
        raise CandidateRankerRuntimeError(message) from cause

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _load_json(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._fail(f"Ranker artifact could not be read: {path.name}.", cause=exc)
        if not isinstance(value, dict):
            self._fail(f"Ranker artifact must contain a JSON object: {path.name}.")
        return value

    def _validate_bundle(self) -> None:
        manifest_path = self.artifact_dir / "manifest.json"
        contract_path = self.artifact_dir / "feature_contract.json"
        model_path = self.artifact_dir / "model.cbm"
        for path in (manifest_path, contract_path, model_path):
            if not path.is_file():
                self._fail(f"Ranker artifact is missing: {path.name}.")

        manifest = self._load_json(manifest_path)
        contract = self._load_json(contract_path)

        if manifest.get("model_version") != EXPECTED_MODEL_VERSION:
            self._fail("Ranker model version does not match research-v1.")
        if manifest.get("status") != EXPECTED_MODEL_STATUS:
            self._fail("Ranker model is not marked EXPERIMENTAL_SYNTHETIC.")
        if manifest.get("feature_contract_version") != FEATURE_SCHEMA_VERSION:
            self._fail("Ranker manifest feature schema does not match the application contract.")
        if contract.get("version") != FEATURE_SCHEMA_VERSION:
            self._fail("Ranker feature contract version does not match the application contract.")
        if tuple(contract.get("input_features", ())) != EXPECTED_FEATURES:
            self._fail("Ranker feature ordering does not match the frozen research-v1 contract.")
        if set(contract.get("eligible_candidates", ())) != ELIGIBLE_STATUSES:
            self._fail("Ranker eligible-candidate contract is incompatible with the application.")
        if set(contract.get("never_rank", ())) != {"INSUFFICIENT_DATA", "REJECTED"}:
            self._fail("Ranker never-rank safety contract is incompatible with the application.")

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            self._fail("Ranker manifest artifact metadata is missing.")
        for filename in ("feature_contract.json", "model.cbm"):
            metadata = artifacts.get(filename)
            path = self.artifact_dir / filename
            if not isinstance(metadata, dict):
                self._fail(f"Ranker manifest metadata is missing for {filename}.")
            if metadata.get("bytes") != path.stat().st_size:
                self._fail(f"Ranker artifact size check failed for {filename}.")
            if metadata.get("sha256") != self._sha256(path):
                self._fail(f"Ranker artifact checksum failed for {filename}.")

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._unavailable_reason is not None:
            raise CandidateRankerRuntimeError(self._unavailable_reason)

        self._validate_bundle()
        try:
            from catboost import CatBoostRanker
        except Exception as exc:  # pragma: no cover - depends on environment
            self._fail("CatBoost runtime dependency is unavailable.", cause=exc)

        try:
            model = CatBoostRanker()
            model.load_model(str(self.artifact_dir / "model.cbm"))
        except Exception as exc:
            self._fail("CatBoost research-v1 model failed to load.", cause=exc)
        self._model = model
        return model

    @staticmethod
    def _vector(features: CandidateFeatures) -> list[float]:
        if features.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise CandidateRankerRuntimeError("Candidate feature schema version mismatch.")
        if features.safety_status not in ELIGIBLE_STATUSES:
            raise CandidateRankerRuntimeError(
                "Experimental CatBoost ranker only accepts SAFE or CONDITIONALLY_SAFE candidates."
            )
        return [
            float(features.duration_minutes),
            float(features.affected_students),
            float(features.confirmed_conflicts_removed),
            float(features.inferred_conflicts_removed),
            float(features.structural_clashes_removed),
            float(features.conflict_groups_removed),
            float(features.weighted_risk_reduction),
            float(features.day_distance),
            float(features.time_shift_minutes),
            float(features.missing_metadata_count),
            1.0 if features.late_slot else 0.0,
            1.0 if features.safety_status == "CONDITIONALLY_SAFE" else 0.0,
        ]

    @staticmethod
    def _bounded_score(raw_score: float) -> int:
        # A monotonic sigmoid keeps CatBoost ordering while satisfying the existing 0-100
        # planning-score contract. This value is NOT a probability or safety estimate.
        if raw_score >= 0:
            z = math.exp(-raw_score)
            bounded = 1.0 / (1.0 + z)
        else:
            z = math.exp(raw_score)
            bounded = z / (1.0 + z)
        return max(0, min(100, round(bounded * 100)))

    def rank(self, features: CandidateFeatures) -> RankerOutput:
        vector = self._vector(features)
        model = self._ensure_model()
        try:
            prediction = model.predict([vector])
            raw_score = float(prediction[0])
        except Exception as exc:
            raise CandidateRankerRuntimeError("CatBoost research-v1 prediction failed.") from exc
        if not math.isfinite(raw_score):
            raise CandidateRankerRuntimeError("CatBoost research-v1 returned a non-finite score.")

        score = self._bounded_score(raw_score)
        return RankerOutput(
            score=score,
            components=(
                RankerScoreComponent(
                    signal="catboost_research_v1",
                    value=score,
                    explanation=(
                        "Synthetic-trained CatBoost ranking signal for an already hard-filtered "
                        "candidate. It is not a probability, safety decision, or real-world "
                        "accuracy claim."
                    ),
                ),
            ),
        )
