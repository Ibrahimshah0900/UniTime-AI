from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth_types import UserRole


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REGISTRATION_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9/-]{2,49}$")


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def normalize_registration_number(value: str) -> str:
    normalized = value.strip().upper()
    if not REGISTRATION_NUMBER_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Registration number must contain 3-50 letters, numbers, hyphens, or slashes."
        )
    return normalized


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Full name is required.")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str | None = Field(default=None, min_length=3, max_length=320)
    email: str | None = Field(default=None, min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_email(value)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_email(value) if "@" in value else normalize_registration_number(value)

    @model_validator(mode="after")
    def require_one_identifier(self):
        if (self.identifier is None) == (self.email is None):
            raise ValueError("Provide exactly one login identifier or legacy email.")
        return self

    @property
    def login_identifier(self) -> str:
        return self.identifier or self.email or ""


class AuthStudentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registration_number: str
    department: str
    program: str
    batch: str
    current_semester: int
    section: str
    academic_status: str
    is_verified: bool
    preferred_name: str | None
    onboarding_completed: bool


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    student_profile: AuthStudentProfileResponse | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserResponse
