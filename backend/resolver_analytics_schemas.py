from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResolverAnalyticsStatusCounts(BaseModel):
    submitted: int = 0
    under_review: int = 0
    resolved: int = 0
    rejected: int = 0
    duplicate: int = 0


class OptionalRateMetric(BaseModel):
    value: float | None
    numerator: int | None
    denominator: int | None
    available: bool
    reason: str | None = None


class ResolverAnalyticsResponse(BaseModel):
    term_id: int
    term_code: str
    generated_at: datetime
    current_confirmed_conflicts: int
    current_inferred_conflicts: int
    current_structural_clashes: int
    current_verified_students: int
    current_enrollment_records: int
    current_affected_student_instances: int
    report_status_counts: ResolverAnalyticsStatusCounts
    report_total: int
    report_cluster_count: int
    grouped_duplicate_reports: int
    average_first_resolution_hours: float | None
    resolution_applications: int
    resolution_undos: int
    resolution_redos: int
    confirmed_conflicts_removed_by_applications: int
    structural_clashes_removed_by_applications: int
    shared_resolved_reports: int
    shared_resolution_percentage: float | None
    recommendation_acceptance_rate: OptionalRateMetric
    undo_rate: OptionalRateMetric
    redo_rate: OptionalRateMetric
    important_note: str
