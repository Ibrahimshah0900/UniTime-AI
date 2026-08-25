from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )

    entry_kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="course",
    )

    course_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
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
        index=True,
    )

    day: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
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

    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
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

    old_day: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    new_day: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    old_start_time: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )

    new_start_time: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )

    old_end_time: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )

    new_end_time: Mapped[Optional[str]] = mapped_column(
        String(10),
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
    email: _AuthMapped[Optional[str]] = _auth_mapped_column(
        _AuthString(320),
        nullable=True,
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
    token_version: _AuthMapped[int] = _auth_mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    must_change_password: _AuthMapped[bool] = _auth_mapped_column(
        _AuthBoolean,
        nullable=False,
        default=False,
        server_default="0",
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
    student_profile: _AuthMapped[Optional["StudentProfile"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="StudentProfile.user_id",
    )


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint(
            "current_semester >= 1 AND current_semester <= 16",
            name="ck_student_profiles_current_semester",
        ),
        CheckConstraint(
            "academic_status IN ('active','on_leave','graduated','suspended')",
            name="ck_student_profiles_academic_status",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    registration_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    program: Mapped[str] = mapped_column(String(120), nullable=False)
    batch: Mapped[str] = mapped_column(String(40), nullable=False)
    current_semester: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    academic_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    preferred_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
        onupdate=_auth_utc_now,
    )
    user: Mapped[User] = relationship(
        back_populates="student_profile",
        foreign_keys=[user_id],
    )


class AcademicTerm(Base):
    __tablename__ = "academic_terms"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planning','active','archived')",
            name="ck_academic_terms_status",
        ),
        CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on",
            name="ck_academic_terms_date_order",
        ),
        Index(
            "uq_academic_terms_single_active",
            "status",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="planning",
        index=True,
    )
    starts_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
        onupdate=_auth_utc_now,
    )


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "term_id",
            "course_code",
            "section",
            "semester",
            name="uq_student_enrollment_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
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


class FacultyClassAssignment(Base):
    __tablename__ = "faculty_class_assignments"
    __table_args__ = (
        UniqueConstraint(
            "faculty_user_id",
            "term_id",
            "course_code",
            "section",
            "semester",
            name="uq_faculty_class_assignment_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    faculty_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    semester: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        CheckConstraint(
            "class_reminder_minutes IS NULL OR class_reminder_minutes IN (5,10,15,30)",
            name="ck_notification_preferences_reminder_minutes",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    class_reminder_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=15,
    )
    daily_summary_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    daily_summary_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="07:00",
    )
    schedule_change_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    clash_report_updates_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
        onupdate=_auth_utc_now,
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('class_reminder','daily_summary','schedule_change','room_change','time_change','cancellation','clash_report_status')",
            name="ck_notifications_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_auth_utc_now,
        index=True,
    )

class StudentClashReport(Base):
    __tablename__ = "student_clash_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted','under_review','resolved','rejected','duplicate')",
            name="ck_student_clash_reports_status",
        ),
        UniqueConstraint(
            "student_user_id",
            "term_id",
            "conflict_fingerprint",
            name="uq_student_clash_report_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    student_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_registration_number_snapshot: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    student_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    student_email_snapshot: Mapped[Optional[str]] = mapped_column(
        String(320),
        nullable=True,
    )
    student_department_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    student_program_snapshot: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    student_batch_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    student_semester_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    student_section_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    conflict_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duplicate_of_report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("student_clash_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_auth_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_auth_utc_now, onupdate=_auth_utc_now)


class StudentClashReportItem(Base):
    __tablename__ = "student_clash_report_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("student_clash_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timetable_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("timetable_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    section: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    semester: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    day: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    start_time: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    end_time: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)


class StudentClashReportEvent(Base):
    __tablename__ = "student_clash_report_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("student_clash_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_auth_utc_now)
