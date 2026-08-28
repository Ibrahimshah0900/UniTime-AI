from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas import TimetableEntryResponse


class TimetableGenerationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int = Field(gt=0)


class TimetableGenerationProposal(BaseModel):
    offering_id: int
    faculty_user_id: int
    faculty_name: str
    course_code: str
    course_name: str
    semester: int
    section: str
    class_type: Literal["lecture", "lab"]
    room: str
    day: str
    start_time: str
    end_time: str
    duration_minutes: int


class TimetableGenerationPreviewResponse(BaseModel):
    term_id: int
    status: Literal["READY", "BLOCKED"]
    preview_id: str
    complete: bool
    existing_satisfied_entry_ids: list[int]
    existing_satisfied_count: int
    proposed_count: int
    readiness_errors: list[str]
    unscheduled: list[str]
    proposals: list[TimetableGenerationProposal]
    policy_note: str


class TimetableGenerationApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int = Field(gt=0)
    preview_id: str = Field(min_length=64, max_length=64)


class TimetableGenerationApplyResponse(BaseModel):
    success: Literal[True]
    term_id: int
    preview_id: str
    created_count: int
    existing_satisfied_count: int
    entries: list[TimetableEntryResponse]
    message: str
