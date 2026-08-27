from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schedule_matching import (
    normalize_course_code,
    normalize_section,
    normalize_semester,
)
from backend.auth_schemas import UserResponse, normalize_email


class FacultyAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faculty_user_id: int = Field(gt=0)
    term_id: int | None = Field(default=None, gt=0)
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
    term_id: int
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


class FacultyProvisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=320)
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool = True

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Full name is required.")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class FacultyProvisionResponse(BaseModel):
    faculty: UserResponse
    temporary_password: str

class FacultyFreeSlotResponse(BaseModel):
    day: str
    start_time: str
    end_time: str
    duration_minutes: int = Field(gt=0)


class FacultyFreeSlotsResponse(BaseModel):
    term_id: int
    opens_at: str
    closes_at: str
    minimum_minutes: int = Field(gt=0)
    slots: list[FacultyFreeSlotResponse]
    note: str
