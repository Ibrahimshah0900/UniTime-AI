from datetime import time
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.schedule_matching import (
    normalize_course_code,
    normalize_section,
    normalize_semester,
)


AllowedDay = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

AllowedClassType = Literal[
    "lecture",
    "lab",
    "tutorial",
    "online",
    "hybrid",
    "other",
]

AllowedSource = Literal[
    "manual",
    "csv",
    "xlsx",
    "docx",
    "pdf",
    "image",
    "generated",
]

AllowedEntryKind = Literal[
    "course",
    "special_event",
]


class TimetableEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_kind: AllowedEntryKind = "course"

    course_code: str | None = Field(default=None, max_length=50)
    course_name: str | None = Field(default=None, max_length=150)
    semester: str | None = Field(default=None, max_length=50)
    section: str | None = Field(default=None, max_length=50)
    faculty: str | None = Field(default=None, max_length=150)
    room: str | None = Field(default=None, max_length=150)

    day: AllowedDay

    start_time: str
    end_time: str

    class_type: AllowedClassType = "lecture"

    raw_text: str | None = Field(default=None, max_length=500)

    source: AllowedSource = "manual"

    @field_validator(
        "course_name",
        "faculty",
        "room",
        "raw_text",
    )
    @classmethod
    def clean_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value

    @field_validator("course_code")
    @classmethod
    def normalize_optional_course_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_course_code(value)
        return normalized or None

    @field_validator("section")
    @classmethod
    def normalize_optional_section(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_section(value)
        return normalized or None

    @field_validator("semester")
    @classmethod
    def normalize_optional_semester(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_semester(value)
        return normalized or None

    @field_validator(
        "start_time",
        "end_time",
    )
    @classmethod
    def validate_time_format(
        cls,
        value: str,
    ) -> str:
        try:
            parsed = time.fromisoformat(value)

        except ValueError as exc:
            raise ValueError(
                "Time must use HH:MM format, "
                "for example 14:30"
            ) from exc

        return parsed.strftime("%H:%M")

    @model_validator(mode="after")
    def validate_entry(self):
        start = time.fromisoformat(
            self.start_time
        )

        end = time.fromisoformat(
            self.end_time
        )

        if end <= start:
            raise ValueError(
                "end_time must be later than start_time"
            )

        if (
            self.entry_kind == "course"
            and not self.course_code
        ):
            raise ValueError(
                "course_code is required "
                "for course entries"
            )

        if (
            self.entry_kind == "special_event"
            and not self.course_name
        ):
            raise ValueError(
                "course_name is required "
                "for special events"
            )

        return self


class TimetableEntryResponse(
    TimetableEntryCreate
):
    id: int
    term_id: int

    model_config = ConfigDict(
        from_attributes=True
    )

class RoomChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room: str = Field(min_length=1, max_length=150)

    @field_validator("room")
    @classmethod
    def clean_room(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("room is required")
        return normalized


class TimetableTimeChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: AllowedDay
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        try:
            parsed = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "Time must use HH:MM format, for example 14:30"
            ) from exc
        return parsed.strftime("%H:%M")

    @model_validator(mode="after")
    def validate_time_order(self):
        if time.fromisoformat(self.end_time) <= time.fromisoformat(self.start_time):
            raise ValueError("end_time must be later than start_time")
        return self


class TimetableTimeChangeSafetyResponse(BaseModel):
    clashes_before: int
    clashes_after: int
    student_risk_cost_before: int
    student_risk_cost_after: int


class TimetableTimeChangeResponse(BaseModel):
    entry: TimetableEntryResponse
    change_id: int
    safety: TimetableTimeChangeSafetyResponse
