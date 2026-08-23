from datetime import time
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
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
]

AllowedEntryKind = Literal[
    "course",
    "special_event",
]


class TimetableEntryCreate(BaseModel):
    entry_kind: AllowedEntryKind = "course"

    course_code: str | None = None
    course_name: str | None = None
    semester: str | None = None
    section: str | None = None
    faculty: str | None = None
    room: str | None = None

    day: AllowedDay

    start_time: str
    end_time: str

    class_type: AllowedClassType = "lecture"

    raw_text: str | None = None

    source: AllowedSource = "manual"

    @field_validator(
        "course_code",
        "course_name",
        "semester",
        "section",
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

    model_config = ConfigDict(
        from_attributes=True
    )

class RoomChangeRequest(BaseModel):
    room: str