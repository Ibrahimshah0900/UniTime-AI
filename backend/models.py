from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    entry_kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="course",
    )

    course_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    course_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    semester: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    section: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    faculty: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    room: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    day: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    start_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    end_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    class_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="lecture",
    )

    raw_text: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
    )


class TimetableChange(Base):
    __tablename__ = "timetable_changes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    entry_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    change_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    old_room: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    new_room: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )

    reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    undone: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )