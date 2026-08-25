from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from backend.models import TimetableEntry
from backend.scheduling_policy import (
    RankingWeights,
    SchedulingPolicy,
    time_to_minutes,
)


FEATURE_SCHEMA_VERSION = "1.0"


class CandidateFeatures(BaseModel):
    """PII-free, safety-gated input contract for any current or future ranker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_schema_version: Literal["1.0"] = FEATURE_SCHEMA_VERSION
    hard_constraints_passed: Literal[True] = True
    safety_status: Literal["SAFE", "CONDITIONALLY_SAFE", "INSUFFICIENT_DATA"]
    duration_minutes: int = Field(gt=0)
    affected_students: int = Field(ge=0)
    confirmed_conflicts_removed: int = Field(ge=0)
    inferred_conflicts_removed: int = Field(ge=0)
    structural_clashes_removed: int = Field(ge=0)
    conflict_groups_removed: int = Field(ge=0)
    weighted_risk_reduction: int = Field(ge=0)
    day_distance: int = Field(ge=0)
    time_shift_minutes: int = Field(ge=0)
    late_slot: bool
    missing_metadata_count: int = Field(ge=0)


class RankerScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal: str = Field(min_length=1, max_length=100)
    value: int
    explanation: str = Field(min_length=1, max_length=500)


class RankerOutput(BaseModel):
    """A ranker cannot return actions, statuses, or bypass flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: int = Field(ge=0, le=100)
    components: tuple[RankerScoreComponent, ...]


@runtime_checkable
class CandidateRanker(Protocol):
    ranker_id: str
    ranker_version: str

    def rank(self, features: CandidateFeatures) -> RankerOutput:
        """Return a bounded planning score for an already hard-filtered candidate."""


def extract_candidate_features(
    *,
    target: TimetableEntry,
    slot: dict[str, str],
    status: Literal["SAFE", "CONDITIONALLY_SAFE", "INSUFFICIENT_DATA"],
    duration_minutes: int,
    affected_students: int,
    confirmed_removed: int,
    inferred_removed: int,
    clashes_removed: int,
    groups_removed: int,
    weighted_risk_before: int,
    weighted_risk_after: int,
    missing_metadata_count: int,
    policy: SchedulingPolicy,
) -> CandidateFeatures:
    day_order = {day: index for index, day in enumerate(policy.operating_days)}
    source_day_index = day_order.get(target.day, len(day_order))
    destination_day_index = day_order[slot["day"]]
    day_distance = abs(source_day_index - destination_day_index)
    return CandidateFeatures(
        safety_status=status,
        duration_minutes=duration_minutes,
        affected_students=affected_students,
        confirmed_conflicts_removed=confirmed_removed,
        inferred_conflicts_removed=inferred_removed,
        structural_clashes_removed=clashes_removed,
        conflict_groups_removed=groups_removed,
        weighted_risk_reduction=max(
            weighted_risk_before - weighted_risk_after,
            0,
        ),
        day_distance=day_distance,
        time_shift_minutes=abs(
            time_to_minutes(target.start_time)
            - time_to_minutes(slot["start_time"])
        ),
        late_slot=time_to_minutes(slot["start_time"]) >= 17 * 60,
        missing_metadata_count=missing_metadata_count,
    )


class DeterministicWeightedRanker:
    """Transparent baseline ranker. This is rules/weights, not an ML model."""

    ranker_id = "deterministic_weighted"
    ranker_version = "1.0"

    def __init__(self, weights: RankingWeights) -> None:
        self.weights = weights

    def rank(self, features: CandidateFeatures) -> RankerOutput:
        components: list[RankerScoreComponent] = []

        def add(signal: str, value: int, explanation: str) -> None:
            components.append(
                RankerScoreComponent(
                    signal=signal,
                    value=value,
                    explanation=explanation,
                )
            )

        add(
            "confirmed_conflicts_removed",
            features.confirmed_conflicts_removed
            * self.weights.confirmed_conflict_removed,
            (
                "Removes "
                f"{features.confirmed_conflicts_removed} confirmed "
                "enrollment-backed conflict(s)."
            ),
        )
        add(
            "inferred_conflicts_removed",
            features.inferred_conflicts_removed * self.weights.inferred_conflict_removed,
            f"Removes {features.inferred_conflicts_removed} inferred conflict signal(s).",
        )
        add(
            "structural_clashes_removed",
            features.structural_clashes_removed * self.weights.structural_clash_removed,
            f"Removes {features.structural_clashes_removed} structural clash(es).",
        )
        add(
            "conflict_groups_removed",
            features.conflict_groups_removed * self.weights.conflict_group_removed,
            f"Reduces conflict groups by {features.conflict_groups_removed}.",
        )
        add(
            "affected_students",
            -features.affected_students * self.weights.affected_student_penalty,
            (
                "Moving the offering affects "
                f"{features.affected_students} enrolled student(s)."
            ),
        )
        add(
            "day_distance",
            -features.day_distance * self.weights.day_distance_penalty,
            f"Moves the class {features.day_distance} operating day step(s).",
        )
        half_hour_units = features.time_shift_minutes // 30
        add(
            "time_shift",
            -half_hour_units * self.weights.half_hour_shift_penalty,
            f"Shifts the start time by {features.time_shift_minutes} minute(s).",
        )
        if features.late_slot:
            add(
                "late_slot",
                -self.weights.late_slot_penalty,
                "Destination begins at or after 17:00.",
            )
        if features.safety_status == "CONDITIONALLY_SAFE":
            add(
                "missing_optional_metadata",
                -self.weights.conditional_data_penalty,
                "Important scheduling metadata still requires coordinator confirmation.",
            )
        elif features.safety_status == "INSUFFICIENT_DATA":
            add(
                "insufficient_data",
                -self.weights.insufficient_data_penalty,
                "Required assignment data is missing.",
            )
        raw_score = 50 + sum(component.value for component in components)
        return RankerOutput(
            score=max(0, min(raw_score, 100)),
            components=tuple(components),
        )


def validate_ranker_output(output: object) -> RankerOutput:
    if isinstance(output, RankerOutput):
        return output
    return RankerOutput.model_validate(output)
