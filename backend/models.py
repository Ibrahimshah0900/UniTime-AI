from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
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

# Authentication model imports are kept local to this section so the
# existing timetable model import block remains untouched.
from datetime import UTC as _AuthUTC, datetime as _AuthDatetime
from sqlalchemy import Boolean as _AuthBoolean
from sqlalchemy import CheckConstraint as _AuthCheckConstraint
from sqlalchemy import DateTime as _AuthSQLDateTime
from sqlalchemy import String as _AuthString
from sqlalchemy.orm import Mapped as _AuthMapped
from sqlalchemy.orm import mapped_column as _auth_mapped_column


def _auth_utc_now() -> _AuthDatetime:
    return _AuthDatetime.now(_AuthUTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        _AuthCheckConstraint(
            "role IN ('student','faculty','coordinator','admin')",
            name="ck_users_role",
        ),
    )

    id: _AuthMapped[int] = _auth_mapped_column(
        primary_key=True
    )
    email: _AuthMapped[str] = _auth_mapped_column(
        _AuthString(320),
        nullable=False,
        unique=True,
    )
    full_name: _AuthMapped[str] = _auth_mapped_column(
        _AuthString(200),
        nullable=False,
    )
    password_hash: _AuthMapped[str] = _auth_mapped_column(
        _AuthString(512),
        nullable=False,
    )
    role: _AuthMapped[str] = _auth_mapped_column(
        _AuthString(32),
        nullable=False,
        default="student",
        index=True,
    )
    is_active: _AuthMapped[bool] = _auth_mapped_column(
        _AuthBoolean,
        nullable=False,
        default=True,
    )
    created_at: _AuthMapped[_AuthDatetime] = _auth_mapped_column(
        _AuthSQLDateTime,
        nullable=False,
        default=_auth_utc_now,
    )
    updated_at: _AuthMapped[_AuthDatetime] = _auth_mapped_column(
        _AuthSQLDateTime,
        nullable=False,
        default=_auth_utc_now,
        onupdate=_auth_utc_now,
    )

class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "course_code",
            "section",
            "semester",
            name="uq_student_enrollment_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    semester: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
    )
