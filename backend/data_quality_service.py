from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    AcademicTerm,
    FacultyClassAssignment,
    StudentClashReport,
    StudentClashReportItem,
    StudentEnrollment,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.schedule_matching import (
    DAY_ORDER,
    normalize_course_code,
    section_matches,
    semester_matches,
)
from backend.term_service import get_active_term, get_term


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _minutes(value: str | None) -> int | None:
    if value is None:
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hours, minutes = (int(part) for part in parts)
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _issue(
    *,
    code: str,
    severity: str,
    scope: str,
    entity_type: str,
    entity_id: str | int | None,
    message: str,
    suggestion: str,
    related: list[int] | None = None,
) -> dict:
    return {
        "issue_code": code,
        "severity": severity,
        "scope": scope,
        "entity_type": entity_type,
        "entity_id": None if entity_id is None else str(entity_id),
        "message": message,
        "suggested_correction": suggestion,
        "related_entity_ids": list(related or []),
    }


def _identity_issues(db: Session) -> list[dict]:
    issues: list[dict] = []
    users = list(db.scalars(select(User).order_by(User.id)).all())
    for user in users:
        email = (user.email or "").strip()
        if email and not _EMAIL_PATTERN.fullmatch(email):
            issues.append(
                _issue(
                    code="MALFORMED_USER_EMAIL",
                    severity="warning",
                    scope="global",
                    entity_type="user",
                    entity_id=user.id,
                    message="The account email is not in a conventional address format.",
                    suggestion="Review the official account email or leave it empty when the institutional workflow permits registration-number-only login.",
                )
            )

    email_groups: dict[str, list[int]] = defaultdict(list)
    for user in users:
        if user.email and user.email.strip():
            email_groups[user.email.strip().casefold()].append(user.id)
    for ids in email_groups.values():
        if len(ids) > 1:
            issues.append(
                _issue(
                    code="DUPLICATE_USER_EMAIL_CASE_INSENSITIVE",
                    severity="error",
                    scope="global",
                    entity_type="user",
                    entity_id=None,
                    message=f"{len(ids)} accounts share the same email when compared case-insensitively.",
                    suggestion="Merge or correct the duplicate institutional account records.",
                    related=ids,
                )
            )

    profiles = list(db.scalars(select(StudentProfile).order_by(StudentProfile.user_id)).all())
    registration_groups: dict[str, list[int]] = defaultdict(list)
    for profile in profiles:
        registration = profile.registration_number.strip()
        registration_groups[registration.casefold()].append(profile.user_id)
        if not registration:
            issues.append(
                _issue(
                    code="BLANK_REGISTRATION_NUMBER",
                    severity="critical",
                    scope="global",
                    entity_type="student_profile",
                    entity_id=profile.user_id,
                    message="A student profile has a blank registration number.",
                    suggestion="Restore the canonical institutional registration number before using the profile.",
                )
            )
        if not 1 <= profile.current_semester <= 16:
            issues.append(
                _issue(
                    code="INVALID_STUDENT_SEMESTER",
                    severity="error",
                    scope="global",
                    entity_type="student_profile",
                    entity_id=profile.user_id,
                    message="The student profile semester is outside the supported 1–16 range.",
                    suggestion="Correct the coordinator-controlled current semester value.",
                )
            )
    for ids in registration_groups.values():
        if len(ids) > 1:
            issues.append(
                _issue(
                    code="DUPLICATE_REGISTRATION_NUMBER_CASE_INSENSITIVE",
                    severity="critical",
                    scope="global",
                    entity_type="student_profile",
                    entity_id=None,
                    message=f"{len(ids)} student profiles share the same registration number when compared case-insensitively.",
                    suggestion="Resolve the duplicate institutional identities before timetable or reporting operations continue.",
                    related=ids,
                )
            )
    return issues


def _timetable_issues(entries: list[TimetableEntry]) -> list[dict]:
    issues: list[dict] = []
    duplicate_groups: dict[tuple, list[int]] = defaultdict(list)
    for entry in entries:
        start = _minutes(entry.start_time)
        end = _minutes(entry.end_time)
        if entry.day not in DAY_ORDER:
            issues.append(
                _issue(
                    code="INVALID_TIMETABLE_DAY",
                    severity="error",
                    scope="term",
                    entity_type="timetable_entry",
                    entity_id=entry.id,
                    message="The timetable entry has an unsupported day value.",
                    suggestion="Move the entry to a valid weekday/weekend value supported by UniTime-AI.",
                )
            )
        if start is None or end is None:
            issues.append(
                _issue(
                    code="INVALID_TIMETABLE_TIME",
                    severity="critical",
                    scope="term",
                    entity_type="timetable_entry",
                    entity_id=entry.id,
                    message="The timetable entry contains an invalid HH:MM time.",
                    suggestion="Correct the class start/end time before clash analysis is trusted.",
                )
            )
        elif start >= end:
            issues.append(
                _issue(
                    code="IMPOSSIBLE_TIMETABLE_TIME_RANGE",
                    severity="critical",
                    scope="term",
                    entity_type="timetable_entry",
                    entity_id=entry.id,
                    message="The timetable entry starts at or after its end time.",
                    suggestion="Correct the class time range before publishing the timetable.",
                )
            )
        if getattr(entry, "entry_kind", "course") == "course":
            if not (entry.faculty or "").strip():
                issues.append(
                    _issue(
                        code="MISSING_TIMETABLE_FACULTY",
                        severity="warning",
                        scope="term",
                        entity_type="timetable_entry",
                        entity_id=entry.id,
                        message="A course timetable entry has no faculty value.",
                        suggestion="Assign the responsible faculty member or explicitly mark the offering as TBA according to institutional policy.",
                    )
                )
            if not (entry.room or "").strip():
                issues.append(
                    _issue(
                        code="MISSING_TIMETABLE_ROOM",
                        severity="warning",
                        scope="term",
                        entity_type="timetable_entry",
                        entity_id=entry.id,
                        message="A course timetable entry has no room value.",
                        suggestion="Assign a room/online location before relying on room-safety recommendations.",
                    )
                )

        duplicate_key = (
            entry.entry_kind,
            (entry.course_code or "").strip().casefold(),
            (entry.course_name or "").strip().casefold(),
            (entry.semester or "").strip().casefold(),
            (entry.section or "").strip().casefold(),
            (entry.faculty or "").strip().casefold(),
            (entry.room or "").strip().casefold(),
            entry.day,
            entry.start_time,
            entry.end_time,
            entry.class_type,
        )
        duplicate_groups[duplicate_key].append(entry.id)

    for ids in duplicate_groups.values():
        if len(ids) > 1:
            issues.append(
                _issue(
                    code="DUPLICATE_TIMETABLE_ENTRY",
                    severity="error",
                    scope="term",
                    entity_type="timetable_entry",
                    entity_id=None,
                    message=f"{len(ids)} timetable rows describe the same class occurrence.",
                    suggestion="Keep one authoritative occurrence and remove/import-correct the duplicates after coordinator review.",
                    related=sorted(ids),
                )
            )
    return issues


def _enrollment_issues(
    db: Session,
    *,
    term_id: int,
    entries: list[TimetableEntry],
) -> list[dict]:
    issues: list[dict] = []
    enrollments = list(
        db.scalars(
            select(StudentEnrollment)
            .where(StudentEnrollment.term_id == term_id)
            .order_by(StudentEnrollment.id)
        ).all()
    )
    users = {user.id: user for user in db.scalars(select(User)).all()}
    profiles = {
        profile.user_id: profile for profile in db.scalars(select(StudentProfile)).all()
    }
    by_course: dict[str, list[TimetableEntry]] = defaultdict(list)
    for entry in entries:
        if entry.course_code:
            by_course[normalize_course_code(entry.course_code)].append(entry)

    for enrollment in enrollments:
        user = users.get(enrollment.user_id)
        profile = profiles.get(enrollment.user_id)
        if user is None or profile is None:
            issues.append(
                _issue(
                    code="ORPHAN_STUDENT_ENROLLMENT",
                    severity="critical",
                    scope="term",
                    entity_type="student_enrollment",
                    entity_id=enrollment.id,
                    message="An enrollment does not have a complete student account/profile relationship.",
                    suggestion="Repair the institutional identity relationship or remove the invalid enrollment through a controlled data correction.",
                )
            )
            continue
        course_entries = by_course.get(normalize_course_code(enrollment.course_code), [])
        if not course_entries:
            issues.append(
                _issue(
                    code="UNKNOWN_COURSE_OFFERING",
                    severity="error",
                    scope="term",
                    entity_type="student_enrollment",
                    entity_id=enrollment.id,
                    message="The enrollment course has no timetable offering in this term.",
                    suggestion="Import/create the missing course offering or correct the enrollment course code.",
                )
            )
            continue
        matches = [
            entry
            for entry in course_entries
            if section_matches(enrollment.section, entry.section)
            and semester_matches(enrollment.semester, entry.semester)
        ]
        if not matches:
            issues.append(
                _issue(
                    code="ENROLLMENT_OFFERING_MISMATCH",
                    severity="warning",
                    scope="term",
                    entity_type="student_enrollment",
                    entity_id=enrollment.id,
                    message="The enrollment course exists, but no timetable entry matches its section/semester identity.",
                    suggestion="Review the enrollment section/semester or the timetable offering metadata.",
                )
            )
    return issues


def _faculty_assignment_issues(
    db: Session,
    *,
    term_id: int,
    entries: list[TimetableEntry],
) -> list[dict]:
    issues: list[dict] = []
    assignments = list(
        db.scalars(
            select(FacultyClassAssignment)
            .where(FacultyClassAssignment.term_id == term_id)
            .order_by(FacultyClassAssignment.id)
        ).all()
    )
    users = {user.id: user for user in db.scalars(select(User)).all()}
    for assignment in assignments:
        user = users.get(assignment.faculty_user_id)
        if user is None or user.role != "faculty" or not user.is_active:
            issues.append(
                _issue(
                    code="INACTIVE_OR_INVALID_FACULTY_ASSIGNMENT",
                    severity="error",
                    scope="term",
                    entity_type="faculty_class_assignment",
                    entity_id=assignment.id,
                    message="A faculty-class assignment points to a missing, inactive, or non-faculty account.",
                    suggestion="Reassign the offering to an active faculty account or correct the account role/status.",
                )
            )
        matching = [
            entry
            for entry in entries
            if entry.course_code
            and normalize_course_code(entry.course_code)
            == normalize_course_code(assignment.course_code)
            and section_matches(assignment.section, entry.section)
            and semester_matches(assignment.semester, entry.semester)
        ]
        if not matching:
            issues.append(
                _issue(
                    code="FACULTY_ASSIGNMENT_WITHOUT_TIMETABLE_OFFERING",
                    severity="warning",
                    scope="term",
                    entity_type="faculty_class_assignment",
                    entity_id=assignment.id,
                    message="A faculty assignment has no matching timetable offering in this term.",
                    suggestion="Create/import the offering or correct the assignment course/section/semester identity.",
                )
            )
    return issues


def _report_integrity_issues(db: Session, *, term_id: int) -> list[dict]:
    issues: list[dict] = []
    open_reports = list(
        db.scalars(
            select(StudentClashReport)
            .where(
                StudentClashReport.term_id == term_id,
                StudentClashReport.status.in_(["submitted", "under_review"]),
            )
            .order_by(StudentClashReport.id)
        ).all()
    )
    if not open_reports:
        return issues
    report_ids = [report.id for report in open_reports]
    items = list(
        db.scalars(
            select(StudentClashReportItem)
            .where(StudentClashReportItem.report_id.in_(report_ids))
            .order_by(StudentClashReportItem.id)
        ).all()
    )
    stale_by_report: dict[int, list[int]] = defaultdict(list)
    for item in items:
        if item.timetable_entry_id is None:
            stale_by_report[item.report_id].append(item.id)
    for report_id, item_ids in stale_by_report.items():
        issues.append(
            _issue(
                code="OPEN_REPORT_WITH_STALE_TIMETABLE_REFERENCE",
                severity="warning",
                scope="term",
                entity_type="student_clash_report",
                entity_id=report_id,
                message="An open clash report contains a class snapshot whose live timetable entry no longer exists.",
                suggestion="Review the report against the current timetable and close it only with a verified resolution/rejection decision.",
                related=item_ids,
            )
        )
    return issues


def run_data_quality_report(db: Session, *, term_id: int | None = None) -> dict:
    term: AcademicTerm = get_active_term(db) if term_id is None else get_term(db, term_id)
    entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == term.id)
            .order_by(TimetableEntry.id)
        ).all()
    )
    issues = []
    issues.extend(_identity_issues(db))
    issues.extend(_timetable_issues(entries))
    issues.extend(_enrollment_issues(db, term_id=term.id, entries=entries))
    issues.extend(_faculty_assignment_issues(db, term_id=term.id, entries=entries))
    issues.extend(_report_integrity_issues(db, term_id=term.id))

    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    issues.sort(
        key=lambda item: (
            severity_order[item["severity"]],
            item["issue_code"],
            item["entity_type"],
            item["entity_id"] or "",
        )
    )
    counts = Counter(issue["severity"] for issue in issues)
    return {
        "term_id": term.id,
        "term_code": term.code,
        "generated_at": _utc_now(),
        "summary": {
            "total": len(issues),
            "critical": counts["critical"],
            "error": counts["error"],
            "warning": counts["warning"],
            "info": counts["info"],
        },
        "issues": issues,
        "important_note": (
            "This endpoint is read-only. Findings are diagnostics, not automatic repairs. "
            "Capacity/equipment checks are intentionally omitted because those facts are not modeled reliably yet."
        ),
    }
