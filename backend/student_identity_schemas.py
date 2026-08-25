from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth_schemas import normalize_email, normalize_registration_number


class AcademicStatus(str, Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    GRADUATED = "graduated"
    SUSPENDED = "suspended"


def normalize_required_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("Value is required.")
    return normalized


def normalize_optional_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return normalize_email(value)


class StudentProvisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_number: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    department: str = Field(min_length=1, max_length=100)
    program: str = Field(min_length=1, max_length=120)
    batch: str = Field(min_length=1, max_length=40)
    current_semester: int = Field(ge=1, le=16)
    section: str = Field(min_length=1, max_length=50)
    academic_status: AcademicStatus = AcademicStatus.ACTIVE
    is_verified: bool = True
    is_active: bool = True
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("registration_number")
    @classmethod
    def validate_registration_number(cls, value: str) -> str:
        return normalize_registration_number(value)

    @field_validator("full_name", "department", "program", "batch", "section")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_optional_email(str(value))


class StudentIdentityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_number: str | None = Field(default=None, min_length=3, max_length=50)
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    program: str | None = Field(default=None, min_length=1, max_length=120)
    batch: str | None = Field(default=None, min_length=1, max_length=40)
    current_semester: int | None = Field(default=None, ge=1, le=16)
    section: str | None = Field(default=None, min_length=1, max_length=50)
    academic_status: AcademicStatus | None = None
    is_verified: bool | None = None
    is_active: bool | None = None

    @field_validator("registration_number")
    @classmethod
    def validate_registration_number(cls, value: str | None) -> str | None:
        return None if value is None else normalize_registration_number(value)

    @field_validator("full_name", "department", "program", "batch", "section")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return None if value is None else normalize_required_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_optional_email(str(value))

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one student identity field must be updated.")
        return self


class StudentIdentityResponse(BaseModel):
    user_id: int
    registration_number: str
    full_name: str
    institutional_email: str | None
    department: str
    program: str
    batch: str
    current_semester: int
    section: str
    academic_status: AcademicStatus
    is_verified: bool
    is_active: bool
    must_change_password: bool
    preferred_name: str | None
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime


class StudentProvisionResponse(BaseModel):
    student: StudentIdentityResponse
    temporary_password: str


class StudentIdentityListResponse(BaseModel):
    students: list[StudentIdentityResponse]
    total: int
    offset: int
    limit: int


class StudentOnboardingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: str | None = Field(default=None, max_length=100)
    complete_onboarding: Literal[True]

    @field_validator("preferred_name")
    @classmethod
    def normalize_preferred_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_required_text(value)


class TemporaryCredentialResponse(BaseModel):
    registration_number: str
    temporary_password: str
    must_change_password: Literal[True] = True


class RosterImportError(BaseModel):
    row: int | None
    field: str | None = None
    type: str
    message: str


class RosterImportCredential(BaseModel):
    registration_number: str
    temporary_password: str


class RosterImportResponse(BaseModel):
    filename: str
    rows_read: int
    would_create: int
    would_update: int
    duplicates: int
    invalid: int
    can_apply: bool
    applied: bool
    dry_run: bool
    errors: list[RosterImportError]
    credentials: list[RosterImportCredential] = Field(default_factory=list)
