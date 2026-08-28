from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schedule_matching import (
    normalize_course_code,
    normalize_section,
)
from backend.scheduling_policy import DEFAULT_SCHEDULING_POLICY, time_to_minutes


FacultyDesignation = Literal["lecturer", "assistant_professor"]
OfferingClassType = Literal["lecture", "lab"]


class CourseOfferingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int = Field(gt=0)
    course_code: str = Field(min_length=1, max_length=50)
    course_name: str = Field(min_length=1, max_length=150)
    semester: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=50)
    class_type: OfferingClassType
    duration_minutes: int = Field(ge=30, le=240)
    room: str | None = Field(default=None, max_length=150)

    @field_validator("course_code")
    @classmethod
    def normalize_course(cls, value: str) -> str:
        normalized = normalize_course_code(value)
        if not normalized:
            raise ValueError("Course code is required.")
        return normalized

    @field_validator("course_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Course name is required.")
        return normalized

    @field_validator("section")
    @classmethod
    def normalize_offering_section(cls, value: str) -> str:
        normalized = normalize_section(value)
        if not normalized:
            raise ValueError("Section is required.")
        return normalized

    @field_validator("room")
    @classmethod
    def normalize_room(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CourseOfferingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str | None = Field(default=None, min_length=1, max_length=50)
    course_name: str | None = Field(default=None, min_length=1, max_length=150)
    semester: int | None = Field(default=None, ge=1, le=8)
    section: str | None = Field(default=None, min_length=1, max_length=50)
    class_type: OfferingClassType | None = None
    duration_minutes: int | None = Field(default=None, ge=30, le=240)
    room: str | None = Field(default=None, max_length=150)

    @field_validator("course_code")
    @classmethod
    def normalize_course(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_course_code(value)
        if not normalized:
            raise ValueError("Course code is required.")
        return normalized

    @field_validator("course_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Course name is required.")
        return normalized

    @field_validator("section")
    @classmethod
    def normalize_offering_section(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_section(value)
        if not normalized:
            raise ValueError("Section is required.")
        return normalized

    @field_validator("room")
    @classmethod
    def normalize_room(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CourseOfferingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term_id: int
    course_code: str
    course_name: str
    semester: int
    section: str
    class_type: OfferingClassType
    duration_minutes: int
    room: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class FacultyTeachingProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: FacultyDesignation


class FacultyWorkloadResponse(BaseModel):
    faculty_user_id: int
    faculty_name: str
    faculty_email: str
    designation: FacultyDesignation | None
    profile_configured: bool
    term_id: int
    distinct_subjects_assigned: int = Field(ge=0)
    maximum_subjects: int | None = Field(default=None, ge=1)
    remaining_capacity: int | None = Field(default=None, ge=0)
    subject_codes: list[str]


class FacultyAvailabilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int = Field(gt=0)
    day: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        minute_value = time_to_minutes(value)
        return f"{minute_value // 60:02d}:{minute_value % 60:02d}"

    @model_validator(mode="after")
    def validate_window(self):
        start = time_to_minutes(self.start_time)
        end = time_to_minutes(self.end_time)
        if start >= end:
            raise ValueError("Availability end_time must be after start_time.")
        if start < time_to_minutes(DEFAULT_SCHEDULING_POLICY.opens_at):
            raise ValueError("Availability starts before institutional operating hours.")
        if end > time_to_minutes(DEFAULT_SCHEDULING_POLICY.closes_at):
            raise ValueError("Availability ends after institutional operating hours.")
        return self


class ManagedFacultyAvailabilityCreate(FacultyAvailabilityCreate):
    faculty_user_id: int = Field(gt=0)


class FacultyAvailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term_id: int
    faculty_user_id: int
    day: str
    start_time: str
    end_time: str
    created_at: datetime
    updated_at: datetime
