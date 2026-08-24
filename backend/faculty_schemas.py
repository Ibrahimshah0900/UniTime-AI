from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schedule_matching import (
    normalize_course_code,
    normalize_section,
    normalize_semester,
)


class FacultyAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faculty_user_id: int = Field(gt=0)
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
    def normalize_assignment_section(cls, value: str) -> str:
        normalized = normalize_section(value)
        if not normalized:
            raise ValueError("Value is required.")
        return normalized

    @field_validator("semester")
    @classmethod
    def normalize_assignment_semester(cls, value: str) -> str:
        normalized = normalize_semester(value)
        if not normalized:
            raise ValueError("Value is required.")
        return normalized


class FacultyAssignmentResponse(BaseModel):
    id: int
    faculty_user_id: int
    faculty_name: str
    faculty_email: str
    course_code: str
    section: str
    semester: str
    created_by_user_id: int | None
    created_at: datetime


class FacultyDirectoryEntryResponse(BaseModel):
    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class FacultyDirectoryResponse(BaseModel):
    faculty: list[FacultyDirectoryEntryResponse]
    total: int
    offset: int
    limit: int
