from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ClashReportStatus = Literal[
    "submitted",
    "under_review",
    "resolved",
    "rejected",
    "duplicate",
]
ClashReportResolutionReason = Literal[
    "timetable_changed",
    "enrollment_corrected",
    "course_dropped",
    "other_verified_correction",
]


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


class ClashReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timetable_entry_ids: list[int] = Field(min_length=2, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)
    evidence_reference: str | None = Field(default=None, max_length=500)

    @field_validator("timetable_entry_ids")
    @classmethod
    def validate_entry_ids(cls, value: list[int]) -> list[int]:
        if any(entry_id <= 0 for entry_id in value):
            raise ValueError("Timetable entry IDs must be positive integers.")
        if len(set(value)) != len(value):
            raise ValueError("Timetable entry IDs must be unique.")
        return value

    @field_validator("notes", "evidence_reference")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class ClashReportReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ClashReportStatus
    resolution_note: str | None = Field(default=None, max_length=2000)
    resolution_reason: ClashReportResolutionReason | None = None
    duplicate_of_report_id: int | None = Field(default=None, gt=0)

    @field_validator("resolution_note")
    @classmethod
    def clean_resolution_note(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def validate_status_fields(self):
        terminal_statuses = {"resolved", "rejected", "duplicate"}
        if self.status in terminal_statuses and self.resolution_note is None:
            raise ValueError(
                "A resolution note is required when resolving, rejecting, "
                "or marking a report as duplicate."
            )
        if self.status == "duplicate" and self.duplicate_of_report_id is None:
            raise ValueError(
                "duplicate_of_report_id is required for duplicate reports."
            )
        if self.status != "duplicate" and self.duplicate_of_report_id is not None:
            raise ValueError(
                "duplicate_of_report_id is only valid for duplicate reports."
            )
        if self.status not in terminal_statuses and self.resolution_note is not None:
            raise ValueError(
                "resolution_note is only valid for a terminal report status."
            )
        if self.status == "resolved" and self.resolution_reason is None:
            raise ValueError("resolution_reason is required for resolved reports.")
        if self.status != "resolved" and self.resolution_reason is not None:
            raise ValueError(
                "resolution_reason is only valid when resolving a report."
            )
        return self


class ClashReportItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timetable_entry_id: int | None
    course_code: str
    section: str | None
    semester: str | None
    day: str | None
    start_time: str | None
    end_time: str | None


class ClashReportEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    action: str
    from_status: str | None
    to_status: str | None
    note: str | None
    created_at: datetime


class ClashReportSummaryResponse(BaseModel):
    id: int
    term_id: int
    student_user_id: int
    student_registration_number: str
    student_name: str
    student_email: str | None
    student_department: str
    student_program: str
    student_batch: str
    student_semester: int
    student_section: str
    conflict_fingerprint: str
    status: ClashReportStatus
    notes: str | None
    evidence_reference: str | None
    duplicate_of_report_id: int | None
    resolution_note: str | None
    resolution_reason: ClashReportResolutionReason | None
    created_at: datetime
    updated_at: datetime
    items: list[ClashReportItemResponse]


class ClashReportDetailResponse(ClashReportSummaryResponse):
    events: list[ClashReportEventResponse]


class ClashReportListResponse(BaseModel):
    reports: list[ClashReportSummaryResponse]
    total: int
    offset: int
    limit: int


class ClashReportClusterClassResponse(BaseModel):
    timetable_entry_id: int | None
    course_code: str
    section: str | None
    semester: str | None
    day: str | None
    start_time: str | None
    end_time: str | None


class ClashReportClusterStatusCountsResponse(BaseModel):
    submitted: int = 0
    under_review: int = 0
    resolved: int = 0
    rejected: int = 0
    duplicate: int = 0


class ClashReportClusterResponse(BaseModel):
    term_id: int
    conflict_fingerprint: str
    report_ids: list[int]
    open_report_ids: list[int]
    timetable_entry_ids: list[int]
    reported_classes: list[ClashReportClusterClassResponse]
    report_count: int
    open_report_count: int
    reporting_student_count: int
    verified_affected_student_count: int
    enrollment_coverage: Literal["complete", "partial", "none"]
    current_timetable_overlap: bool
    status_counts: ClashReportClusterStatusCountsResponse
    first_reported_at: datetime
    latest_reported_at: datetime


class ClashReportClusterListResponse(BaseModel):
    clusters: list[ClashReportClusterResponse]
    total: int
    offset: int
    limit: int


CandidateSafetyStatus = Literal[
    "SAFE",
    "CONDITIONALLY_SAFE",
    "INSUFFICIENT_DATA",
    "REJECTED",
]


class CandidateTimeSlotResponse(BaseModel):
    day: str
    start_time: str
    end_time: str


class CandidateBlockedPeriodResponse(CandidateTimeSlotResponse):
    reason: str


class CandidatePolicyResponse(BaseModel):
    operating_days: list[str]
    opens_at: str
    closes_at: str
    slot_interval_minutes: int
    blocked_periods: list[CandidateBlockedPeriodResponse]


class CandidateCheckResponse(BaseModel):
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    detail: str


class CandidateScoreComponentResponse(BaseModel):
    signal: str
    value: int
    explanation: str


class CandidateRankerResponse(BaseModel):
    ranker_id: str
    ranker_version: str


class CandidateFeaturesResponse(BaseModel):
    feature_schema_version: Literal["1.0"]
    hard_constraints_passed: Literal[True]
    safety_status: Literal["SAFE", "CONDITIONALLY_SAFE", "INSUFFICIENT_DATA"]
    duration_minutes: int
    affected_students: int
    confirmed_conflicts_removed: int
    inferred_conflicts_removed: int
    structural_clashes_removed: int
    conflict_groups_removed: int
    weighted_risk_reduction: int
    day_distance: int
    time_shift_minutes: int
    late_slot: bool
    missing_metadata_count: int


class CandidateImpactResponse(BaseModel):
    affected_students: int
    confirmed_conflicts_before: int
    confirmed_conflicts_after: int
    confirmed_conflicts_removed: int
    new_confirmed_conflicts: int
    student_risks_before: int
    student_risks_after: int
    structural_clashes_before: int
    structural_clashes_after: int
    conflict_groups_before: int
    conflict_groups_after: int
    weighted_risk_before: int
    weighted_risk_after: int
    timetable_entries_changed: int


class SafeResolutionCandidateResponse(BaseModel):
    candidate_id: str
    status: CandidateSafetyStatus
    actionable_without_confirmation: bool
    entry_id: int
    course_code: str | None
    course_name: str | None
    section: str | None
    move_from: CandidateTimeSlotResponse
    move_to: CandidateTimeSlotResponse
    duration_minutes: int
    rank_score: int
    score_components: list[CandidateScoreComponentResponse]
    ranker: CandidateRankerResponse
    features: CandidateFeaturesResponse
    checks: list[CandidateCheckResponse]
    missing_data: list[str]
    rejection_reasons: list[str]
    impact: CandidateImpactResponse


class RejectedResolutionCandidateResponse(BaseModel):
    candidate_id: str
    entry_id: int
    move_to: CandidateTimeSlotResponse
    status: Literal["REJECTED"]
    rejection_reasons: list[str]
    checks: list[CandidateCheckResponse] = Field(default_factory=list)


class ResolutionCandidateSummaryResponse(BaseModel):
    generated: int
    safe: int
    conditionally_safe: int
    insufficient_data: int
    rejected: int


class ClashReportResolutionCandidatesResponse(BaseModel):
    report_id: int
    report_status: ClashReportStatus
    report_entry_ids: list[int]
    target_entry_ids: list[int]
    policy: CandidatePolicyResponse
    summary: ResolutionCandidateSummaryResponse
    candidates: list[SafeResolutionCandidateResponse]
    rejected_candidates: list[RejectedResolutionCandidateResponse]
    important_note: str


class ClashReportResolutionApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_entry_id: int = Field(gt=0)
    resolution_note: str = Field(min_length=1, max_length=2000)
    confirm_conditional: bool = False

    @field_validator("resolution_note")
    @classmethod
    def clean_resolution_note(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("resolution_note must contain non-whitespace text.")
        return normalized


class ClashReportResolutionApplyResponse(BaseModel):
    success: Literal[True]
    message: str
    report_id: int
    report_status: Literal["resolved"]
    change_id: int
    candidate_id: str
    safety_status: Literal["SAFE", "CONDITIONALLY_SAFE"]
    conditional_confirmation_recorded: bool
    resolved_report_ids: list[int]
    resolved_report_count: int
    applied_candidate: SafeResolutionCandidateResponse
    report: ClashReportDetailResponse
