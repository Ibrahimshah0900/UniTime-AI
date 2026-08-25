from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schedule_matching import (
    normalize_course_code,
    normalize_section,
    normalize_semester,
)


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str = Field(min_length=1, max_length=50)
    section: str = Field(min_length=1, max_length=50)
    semester: str = Field(min_length=1, max_length=50)

    @field_validator("course_code")
    @classmethod
    def normalize_course(cls, value: str) -> str:
        normalized = normalize_course_code(value)
        if not normalized:
            raise ValueError("Value is required.")
        return normalized

    @field_validator("section")
    @classmethod
    def normalize_enrollment_section(cls, value: str) -> str:
        normalized = normalize_section(value)
        if not normalized:
            raise ValueError("Value is required.")
        return normalized

    @field_validator("semester")
    @classmethod
    def normalize_enrollment_semester(cls, value: str) -> str:
        normalized = normalize_semester(value)
        if not normalized:
            raise ValueError("Value is required.")
        return normalized


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term_id: int
    user_id: int
    course_code: str
    section: str
    semester: str
    created_at: datetime


class EnrollmentTimetableClassResponse(BaseModel):
    id: int
    course_code: str | None
    course_name: str | None
    section: str | None
    semester: str | None
    faculty: str | None
    room: str | None
    day: str
    start_time: str
    end_time: str


class EnrollmentOverlapResponse(BaseModel):
    proposed_class: EnrollmentTimetableClassResponse
    conflicts_with: EnrollmentTimetableClassResponse
    day: str
    overlap_start: str
    overlap_end: str


class EnrollmentAlternateSectionResponse(BaseModel):
    section: str
    timetable_entry_ids: list[int]
    conflict_free: bool
    validation_status: Literal["timetable_only_unverified"]
    limitations: list[str]


class EnrollmentConflictValidationResponse(BaseModel):
    course_code: str
    section: str
    semester: str
    mapped_timetable_entry_ids: list[int]
    has_conflicts: bool
    conflicts: list[EnrollmentOverlapResponse]
    alternate_sections: list[EnrollmentAlternateSectionResponse]
    limitations: list[str]


class EnrollmentCreateResponse(EnrollmentResponse):
    conflict_validation: EnrollmentConflictValidationResponse
