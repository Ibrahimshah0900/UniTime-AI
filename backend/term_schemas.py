from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AcademicTermStatus = Literal["planning", "active", "archived"]
TERM_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")


class AcademicTermCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = re.sub(r"\s+", "-", value.strip().upper())
        if not TERM_CODE_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Term code may contain only letters, numbers, hyphens, and underscores."
            )
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Term name is required.")
        return normalized

    @model_validator(mode="after")
    def validate_date_order(self):
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValueError("starts_on must be on or before ends_on.")
        return self


class AcademicTermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    status: AcademicTermStatus
    starts_on: date | None
    ends_on: date | None
    created_by_user_id: int | None
    activated_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AcademicTermListResponse(BaseModel):
    terms: list[AcademicTermResponse]
    total: int
    active_term_id: int | None
