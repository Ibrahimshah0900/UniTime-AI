from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationModel(BaseModel):
    """Typed operation payload that preserves forward-compatible additions."""

    model_config = ConfigDict(extra="allow")


class FlexibleOperationResponse(OperationModel):
    """Compatibility contract for mutation responses with endpoint-specific details."""


class RootResponse(BaseModel):
    app: str
    status: str
    version: str
    phase: str


class HealthResponse(BaseModel):
    status: str
    database: str


class MigrationReadinessResponse(BaseModel):
    managed: bool
    revision: str
    expected_revision: str
    at_head: bool


class ReadinessResponse(BaseModel):
    status: str
    database: str
    migrations: MigrationReadinessResponse


class TimetableImportError(BaseModel):
    row: int
    type: str
    details: list[dict[str, Any]]


class TimetableImportResponse(BaseModel):
    filename: str
    rows_read: int
    imported: int
    duplicates: int
    invalid: int
    column_mapping: dict[str, str]
    errors: list[TimetableImportError]


class NotificationReadAllResponse(BaseModel):
    updated: int


class OperationEntryResponse(OperationModel):
    id: int
    entry_kind: str | None = None
    course_code: str | None
    course_name: str | None
    course_levels: list[int] = Field(default_factory=list)
    semester: str | None
    section: str | None
    faculty: str | None
    room: str | None
    day: str | None = None
    start_time: str
    end_time: str
    class_type: str | None = None
    raw_text: str | None = None


class TimeOverlapResponse(BaseModel):
    entry_1_time: str
    entry_2_time: str


class StructuralClashResponse(OperationModel):
    type: str
    severity: str
    day: str
    overlap: TimeOverlapResponse
    reason: str
    entry_1: OperationEntryResponse
    entry_2: OperationEntryResponse


class ClashCollectionResponse(BaseModel):
    total: int
    clashes: list[StructuralClashResponse]


class AlternativeRoomResponse(OperationModel):
    room: str
    room_type: str
    weekly_usage_count: int
    score: float
    reasons: list[str]


class RoomEntrySuggestionResponse(OperationModel):
    entry_id: int
    course_code: str | None
    course_name: str | None
    current_room: str | None
    day: str
    start_time: str
    end_time: str
    class_type: str
    alternative_rooms: list[AlternativeRoomResponse]


class BestRoomFixResponse(OperationModel):
    entry_id: int
    course_code: str | None
    course_name: str | None
    from_room: str | None
    to_room: str
    day: str
    start_time: str
    end_time: str
    score: float
    weekly_usage_count: int
    reasons: list[str]


class RoomResolutionResponse(OperationModel):
    clash_type: str | None
    day: str | None
    reason: str | None
    suggestions: list[RoomEntrySuggestionResponse]
    best_fix: BestRoomFixResponse | None
    error: str | None = None


class RoomSuggestionCollectionResponse(BaseModel):
    room_clashes: int
    resolutions: list[RoomResolutionResponse]


class StudentRiskSummaryResponse(BaseModel):
    total: int
    confirmed: int
    probable: int
    possible: int
    important_note: str


class StudentRiskResponse(OperationModel):
    type: str
    risk_type: str
    risk_level: str
    score: float
    day: str
    overlap: TimeOverlapResponse
    shared_sections: list[str]
    same_course_level: bool
    evidence: list[str]
    limitations: list[str]
    entry_1: OperationEntryResponse
    entry_2: OperationEntryResponse


class StudentRiskCollectionResponse(BaseModel):
    summary: StudentRiskSummaryResponse
    risks: list[StudentRiskResponse]


class TimeWindowResponse(BaseModel):
    start_time: str
    end_time: str


class StudentGroupResponse(OperationModel):
    group_id: int
    type: str
    risk_level: str
    priority_score: float
    day: str
    time_window: TimeWindowResponse
    course_levels: list[int]
    shared_sections: list[str]
    courses_involved: int
    pairwise_risks: int
    entries: list[OperationEntryResponse]
    evidence: list[str]
    limitations: list[str]
    action: str


class StudentGroupSummaryResponse(BaseModel):
    total_groups: int
    confirmed_groups: int
    probable_groups: int
    unique_timetable_entries_involved: int
    important_note: str


class StudentGroupCollectionResponse(BaseModel):
    summary: StudentGroupSummaryResponse
    groups: list[StudentGroupResponse]


class TimeSlotResponse(BaseModel):
    day: str
    start_time: str
    end_time: str


class StudentMoveResponse(OperationModel):
    entry_id: int
    course_code: str | None
    course_name: str | None
    section: str | None
    faculty: str | None
    current_room: str | None
    class_type: str
    move_from: TimeSlotResponse
    move_to: TimeSlotResponse
    score: float
    faculty_available: bool
    room_status: str
    room_available: bool | None
    risk_before: dict[str, int]
    risk_after: dict[str, int]
    risk_cost_before: int
    risk_cost_after: int
    reasons: list[str]


class StudentResolutionResponse(OperationModel):
    group_id: int
    risk_level: str
    priority_score: float
    day: str
    time_window: TimeWindowResponse
    courses_involved: int
    best_fix: StudentMoveResponse | None
    alternatives: list[StudentMoveResponse]
    important_note: str


class StudentResolutionSummaryResponse(BaseModel):
    total_groups: int
    groups_with_suggestion: int
    groups_without_suggestion: int
    fully_feasible_best_fixes: int
    best_fixes_requiring_room: int
    important_note: str


class StudentResolutionCollectionResponse(BaseModel):
    summary: StudentResolutionSummaryResponse
    resolutions: list[StudentResolutionResponse]


class OptimizerSnapshotResponse(BaseModel):
    student_risk_cost: int
    student_risks: dict[str, int]
    student_groups: int
    clashes: dict[str, int]


class OptimizerImprovementValueResponse(BaseModel):
    before: int
    after: int
    reduction: int


class OptimizerImprovementResponse(BaseModel):
    student_risk_cost: OptimizerImprovementValueResponse
    student_risks: OptimizerImprovementValueResponse
    student_groups: OptimizerImprovementValueResponse
    general_clashes: OptimizerImprovementValueResponse


class OptimizerMoveResponse(OperationModel):
    source_group_id: int | None
    entry_id: int
    course_code: str | None
    course_name: str | None
    section: str | None
    faculty: str | None
    room: str | None
    class_type: str | None
    move_from: TimeSlotResponse
    move_to: TimeSlotResponse
    local_score: float | None
    global_score: float | None
    room_status: str | None
    improvement: OptimizerImprovementResponse
    reasons: list[str] = Field(default_factory=list)


class OptimizerCandidateSummaryResponse(BaseModel):
    generated: int
    globally_safe: int
    rejected: int


class GlobalOptimizationResponse(BaseModel):
    baseline: OptimizerSnapshotResponse
    candidate_summary: OptimizerCandidateSummaryResponse
    best_move: OptimizerMoveResponse | None
    ranked_moves: list[OptimizerMoveResponse]
    important_note: str


class OptimizerPlanStepResponse(OptimizerMoveResponse):
    step: int


class OptimizerPlannerStatisticsResponse(BaseModel):
    unique_entries_moved: int
    rejected_during_planning: int


class OptimizerPlanResponse(BaseModel):
    requested_max_steps: int
    planned_steps: int
    stop_reason: str
    baseline: OptimizerSnapshotResponse
    projected_final: OptimizerSnapshotResponse
    overall_improvement: OptimizerImprovementResponse
    planner_statistics: OptimizerPlannerStatisticsResponse
    steps: list[OptimizerPlanStepResponse]
    important_note: str


class OptimizerExecutionMetricsResponse(BaseModel):
    student_risk_cost: int
    total_student_risks: int
    student_groups: int
    general_clashes: int


class OptimizerExecutionResponse(OperationModel):
    term_id: int
    execution_id: str
    status: str
    requested_steps: int
    applied_steps: int
    baseline: OptimizerExecutionMetricsResponse
    final: OptimizerExecutionMetricsResponse
    stop_reason: str | None
    error_message: str | None
    created_at: str | None
    completed_at: str | None


class OptimizerExecutionStepResponse(BaseModel):
    step_number: int
    change_id: int


class OptimizerExecutionDetailResponse(OptimizerExecutionResponse):
    steps: list[OptimizerExecutionStepResponse]


class OptimizerExecutionCollectionResponse(BaseModel):
    executions: list[OptimizerExecutionResponse]


class TimetableChangeResponse(BaseModel):
    id: int
    term_id: int
    entry_id: int
    change_type: str
    old_room: str | None
    new_room: str | None
    old_day: str | None
    new_day: str | None
    old_start_time: str | None
    new_start_time: str | None
    old_end_time: str | None
    new_end_time: str | None
    reason: str | None
    score: float | None
    created_at: str | None
    undone: bool


class ChangeCollectionResponse(BaseModel):
    total: int
    changes: list[TimetableChangeResponse]


class StudentScheduleChangeResponse(BaseModel):
    id: int
    term_id: int
    entry_id: int
    group_id: int
    change_type: str
    old_day: str
    old_start_time: str
    old_end_time: str
    new_day: str
    new_start_time: str
    new_end_time: str
    score: float
    risk_cost_before: int
    risk_cost_after: int
    total_risks_before: int
    total_risks_after: int
    undone: bool
    created_at: str | None


class StudentScheduleChangeCollectionResponse(BaseModel):
    total: int
    changes: list[StudentScheduleChangeResponse]


class AuditStateResponse(OperationModel):
    room: str | None = None
    day: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class AuditItemResponse(OperationModel):
    audit_type: str
    term_id: int
    history_id: int
    entry_id: int
    course_code: str | None
    course_name: str | None
    group_id: int | None = None
    change_type: str
    before: AuditStateResponse
    after: AuditStateResponse
    reason: str | None = None
    risk_cost_before: int | None = None
    risk_cost_after: int | None = None
    score: float | None
    undone: bool
    created_at: str | None


class AuditTrailSummaryResponse(BaseModel):
    total_changes: int
    active_changes: int
    undone_changes: int
    room_changes: int
    timetable_time_changes: int
    student_schedule_changes: int


class AuditTrailResponse(BaseModel):
    summary: AuditTrailSummaryResponse
    audit_trail: list[AuditItemResponse]
