from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_code: str
    section: str
    semester: str
    created_at: datetime
