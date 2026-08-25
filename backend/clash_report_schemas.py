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
    student_name: str
    student_email: str
    status: ClashReportStatus
    notes: str | None
    evidence_reference: str | None
    duplicate_of_report_id: int | None
    resolution_note: str | None
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
