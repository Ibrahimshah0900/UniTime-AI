from __future__ import annotations

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


NotificationType = Literal[
    "class_reminder",
    "daily_summary",
    "schedule_change",
    "room_change",
    "time_change",
    "cancellation",
    "clash_report_status",
]


class NotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_reminder_minutes: Literal[5, 10, 15, 30] | None = 15
    daily_summary_enabled: bool = False
    daily_summary_time: str = "07:00"
    schedule_change_enabled: bool = True
    clash_report_updates_enabled: bool = True

    @field_validator("daily_summary_time")
    @classmethod
    def validate_daily_summary_time(cls, value: str) -> str:
        try:
            parsed = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("daily_summary_time must use HH:MM format.") from exc
        return parsed.strftime("%H:%M")


class NotificationPreferenceResponse(NotificationPreferenceUpdate):
    user_id: int
    updated_at: datetime | None


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: NotificationType
    title: str
    message: str
    payload: dict
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    offset: int
    limit: int


class NotificationJobResponse(BaseModel):
    reminders_created: int
    summaries_created: int
    processed_users: int
    timezone: str
