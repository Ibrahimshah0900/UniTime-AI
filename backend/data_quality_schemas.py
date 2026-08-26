from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DataQualitySeverity = Literal["critical", "error", "warning", "info"]
DataQualityScope = Literal["global", "term"]


class DataQualityIssueResponse(BaseModel):
    issue_code: str
    severity: DataQualitySeverity
    scope: DataQualityScope
    entity_type: str
    entity_id: str | None
    message: str
    suggested_correction: str
    related_entity_ids: list[int] = Field(default_factory=list)


class DataQualitySummaryResponse(BaseModel):
    total: int
    critical: int
    error: int
    warning: int
    info: int


class DataQualityReportResponse(BaseModel):
    term_id: int
    term_code: str
    generated_at: datetime
    summary: DataQualitySummaryResponse
    issues: list[DataQualityIssueResponse]
    important_note: str
