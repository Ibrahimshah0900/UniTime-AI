from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FacultyAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faculty_user_id: int = Field(gt=0)
    course_code: str = Field(min_length=1, max_length=50)
    section: str = Field(min_length=1, max_length=50)
    semester: str = Field(min_length=1, max_length=50)

    @field_validator("course_code", "section", "semester")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
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
