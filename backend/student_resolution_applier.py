from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    Session,
    mapped_column,
)

from backend.clash_detector import detect_clashes
from backend.database import Base
from backend.models import (
    StudentClashReport,
    StudentClashReportEvent,
    StudentClashReportItem,
    TimetableEntry,
)
from backend.enrollment_conflict_graph import build_enrollment_conflict_analysis
from backend.notification_service import (
    add_clash_report_status_notification,
    add_time_change_notifications,
)
from backend.safe_candidate_service import generate_safe_candidates
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
)
from backend.student_conflict_groups import (
    build_student_conflict_groups,
)
from backend.student_conflict_resolver import (
    faculty_is_available,
    get_room_status_for_candidate,
    resolve_student_conflict_group,
)
from backend.term_service import get_active_term, resolve_term_for_write


# ---------------------------------------------------------------------------
# HISTORY MODEL
# ---------------------------------------------------------------------------


class StudentScheduleChange(Base):
    __tablename__ = "student_schedule_changes"
    __table_args__ = (
        CheckConstraint(
            "safety_status IS NULL OR safety_status IN "
            "('SAFE','CONDITIONALLY_SAFE','INSUFFICIENT_DATA','REJECTED')",
            name="ck_student_schedule_changes_safety_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_entries.id"),
        nullable=False,
        index=True,
    )

    group_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_clash_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    candidate_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    safety_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    report_resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    change_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="student_conflict_move",
    )

    old_day: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    old_start_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    old_end_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    new_day: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    new_start_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    new_end_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    reasons_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    risk_cost_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    risk_cost_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_risks_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_risks_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    undone: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------


RISK_WEIGHT = {
    "confirmed": 100,
    "probable": 10,
    "possible": 2,
}


# ---------------------------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------------------------


def get_all_entries(
    db: Session,
    term_id: int | None = None,
) -> list[TimetableEntry]:
    selected_term_id = term_id or get_active_term(db).id
    statement = (
        select(TimetableEntry)
        .where(TimetableEntry.term_id == selected_term_id)
        .order_by(TimetableEntry.id)
    )

    return list(
        db.scalars(statement).all()
    )


def calculate_risk_cost(
    risks: list[dict],
) -> int:
    return sum(
        RISK_WEIGHT.get(
            risk.get("risk_level"),
            0,
        )
        for risk in risks
    )


def calculate_entry_risk_cost(
    risks: list[dict],
    entry_id: int,
) -> int:
    total = 0

    for risk in risks:
        first_id = (
            risk["entry_1"]["id"]
        )

        second_id = (
            risk["entry_2"]["id"]
        )

        if entry_id not in {
            first_id,
            second_id,
        }:
            continue

        total += RISK_WEIGHT.get(
            risk.get("risk_level"),
            0,
        )

    return total


def get_entry_risks(
    risks: list[dict],
    entry_id: int,
) -> list[dict]:
    return [
        risk
        for risk in risks
        if entry_id
        in {
            risk["entry_1"]["id"],
            risk["entry_2"]["id"],
        }
    ]


def parse_reasons(
    change: StudentScheduleChange,
) -> list[str]:
    if not change.reasons_json:
        return []

    try:
        value = json.loads(
            change.reasons_json
        )

        if isinstance(
            value,
            list,
        ):
            return [
                str(item)
                for item in value
            ]

    except json.JSONDecodeError:
        pass

    return []


# ---------------------------------------------------------------------------
# LIVE GROUP LOOKUP
# ---------------------------------------------------------------------------


def get_live_group(
    group_id: int,
    entries: list[TimetableEntry],
    *,
    risks: list[dict] | None = None,
) -> dict:
    selected_risks = risks if risks is not None else analyze_student_conflicts(entries)

    groups = build_student_conflict_groups(
        selected_risks
    )

    for group in groups:
        if (
            group["group_id"]
            == group_id
        ):
            return group

    raise ValueError(
        "Student conflict group was not found "
        "in the current timetable."
    )


# ---------------------------------------------------------------------------
# LIVE BEST FIX
# ---------------------------------------------------------------------------


def get_live_best_fix(
    group_id: int,
    entries: list[TimetableEntry],
    *,
    risks: list[dict] | None = None,
) -> tuple[dict, dict]:
    group = get_live_group(
        group_id,
        entries,
        risks=risks,
    )

    resolution = (
        resolve_student_conflict_group(
            group,
            entries,
        )
    )

    best_fix = resolution.get(
        "best_fix"
    )

    if best_fix is None:
        raise ValueError(
            "No resolution is currently available "
            "for this student conflict group."
        )

    room_status = best_fix.get(
        "room_status"
    )

    if room_status not in {
        "available",
        "online",
    }:
        raise ValueError(
            "The current best fix is not fully feasible. "
            "A room must be assigned before it can be applied."
        )

    return (
        group,
        best_fix,
    )


# ---------------------------------------------------------------------------
# ENTRY STATE VALIDATION
# ---------------------------------------------------------------------------


def validate_entry_state(
    entry: TimetableEntry,
    best_fix: dict,
) -> None:
    move_from = best_fix[
        "move_from"
    ]

    if (
        entry.day
        != move_from["day"]
        or entry.start_time
        != move_from["start_time"]
        or entry.end_time
        != move_from["end_time"]
    ):
        raise ValueError(
            "The timetable entry changed after the "
            "resolution was calculated. Recalculate "
            "student conflict resolutions first."
        )


# ---------------------------------------------------------------------------
# HARD CONSTRAINT VALIDATION
# ---------------------------------------------------------------------------


def validate_destination(
    entry: TimetableEntry,
    best_fix: dict,
    entries: list[TimetableEntry],
) -> dict:
    move_to = best_fix[
        "move_to"
    ]

    faculty_available = (
        faculty_is_available(
            entry,
            day=move_to["day"],
            start_time=move_to[
                "start_time"
            ],
            end_time=move_to[
                "end_time"
            ],
            entries=entries,
        )
    )

    if not faculty_available:
        raise ValueError(
            "The faculty member is no longer "
            "available at the proposed timetable slot."
        )

    room_info = (
        get_room_status_for_candidate(
            entry,
            day=move_to["day"],
            start_time=move_to[
                "start_time"
            ],
            end_time=move_to[
                "end_time"
            ],
            entries=entries,
        )
    )

    if (
        room_info["room_status"]
        not in {
            "available",
            "online",
        }
    ):
        raise ValueError(
            "The room is no longer available "
            "at the proposed timetable slot."
        )

    return {
        "faculty_available": True,
        "room_status": (
            room_info[
                "room_status"
            ]
        ),
        "room_available": (
            room_info[
                "room_available"
            ]
        ),
    }


def validate_specific_destination(
    entry: TimetableEntry,
    *,
    day: str,
    start_time: str,
    end_time: str,
    entries: list[TimetableEntry],
) -> dict:
    faculty_available = (
        faculty_is_available(
            entry,
            day=day,
            start_time=start_time,
            end_time=end_time,
            entries=entries,
        )
    )

    if not faculty_available:
        raise ValueError(
            "The faculty member is not available "
            "at the requested timetable slot."
        )

    room_info = (
        get_room_status_for_candidate(
            entry,
            day=day,
            start_time=start_time,
            end_time=end_time,
            entries=entries,
        )
    )

    if (
        room_info["room_status"]
        not in {
            "available",
            "online",
        }
    ):
        raise ValueError(
            "The room is not available "
            "at the requested timetable slot."
        )

    return {
        "faculty_available": True,
        "room_status": (
            room_info[
                "room_status"
            ]
        ),
        "room_available": (
            room_info[
                "room_available"
            ]
        ),
    }


# ---------------------------------------------------------------------------
# SAFETY COMPARISON
# ---------------------------------------------------------------------------


def compare_general_clashes(
    before: list[dict],
    after: list[dict],
) -> None:
    if len(after) > len(before):
        raise ValueError(
            "The proposed student resolution was rejected "
            "because it creates additional timetable clashes."
        )


def validate_risk_improvement(
    *,
    entry_id: int,
    risks_before: list[dict],
    risks_after: list[dict],
) -> dict[str, int]:
    total_cost_before = (
        calculate_risk_cost(
            risks_before
        )
    )

    total_cost_after = (
        calculate_risk_cost(
            risks_after
        )
    )

    entry_cost_before = (
        calculate_entry_risk_cost(
            risks_before,
            entry_id,
        )
    )

    entry_cost_after = (
        calculate_entry_risk_cost(
            risks_after,
            entry_id,
        )
    )

    if entry_cost_before <= 0:
        raise ValueError(
            "The selected timetable entry no longer "
            "has a student/cohort conflict risk."
        )

    if (
        entry_cost_after
        >= entry_cost_before
    ):
        raise ValueError(
            "The proposed move was rejected because "
            "it does not improve the selected entry's "
            "student/cohort conflict risk."
        )

    if (
        total_cost_after
        > total_cost_before
    ):
        raise ValueError(
            "The proposed move was rejected because "
            "it increases total student/cohort risk."
        )

    confirmed_after = [
        risk
        for risk in get_entry_risks(
            risks_after,
            entry_id,
        )
        if (
            risk["risk_level"]
            == "confirmed"
        )
    ]

    if confirmed_after:
        raise ValueError(
            "The proposed move was rejected because "
            "it creates a confirmed student conflict."
        )

    return {
        "total_cost_before": (
            total_cost_before
        ),
        "total_cost_after": (
            total_cost_after
        ),
        "entry_cost_before": (
            entry_cost_before
        ),
        "entry_cost_after": (
            entry_cost_after
        ),
    }


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------


def create_student_change_record(
    db: Session,
    *,
    group_id: int,
    entry: TimetableEntry,
    old_day: str,
    old_start_time: str,
    old_end_time: str,
    new_day: str,
    new_start_time: str,
    new_end_time: str,
    score: float | None,
    reasons: list[str],
    risk_cost_before: int,
    risk_cost_after: int,
    total_risks_before: int,
    total_risks_after: int,
) -> StudentScheduleChange:
    change = StudentScheduleChange(
        term_id=entry.term_id,
        entry_id=entry.id,
        group_id=group_id,
        change_type=(
            "student_conflict_move"
        ),
        old_day=old_day,
        old_start_time=(
            old_start_time
        ),
        old_end_time=old_end_time,
        new_day=new_day,
        new_start_time=(
            new_start_time
        ),
        new_end_time=new_end_time,
        score=score,
        reasons_json=json.dumps(
            reasons
        ),
        risk_cost_before=(
            risk_cost_before
        ),
        risk_cost_after=(
            risk_cost_after
        ),
        total_risks_before=(
            total_risks_before
        ),
        total_risks_after=(
            total_risks_after
        ),
        undone=False,
    )

    db.add(change)
    db.flush()
    add_time_change_notifications(
        db,
        entry=entry,
        old_day=old_day,
        old_start_time=old_start_time,
        old_end_time=old_end_time,
        event_key=f"student-change:{change.id}",
    )

    return change


# ---------------------------------------------------------------------------
# SAFE APPLY
# ---------------------------------------------------------------------------


def apply_student_resolution(
    db: Session,
    *,
    group_id: int,
) -> dict[str, Any]:
    try:
        entries_before = get_all_entries(
            db
        )

        risks_before = build_enrollment_conflict_analysis(
            db,
            entries_before,
        )["risks"]

        group, best_fix = (
            get_live_best_fix(
                group_id,
                entries_before,
                risks=risks_before,
            )
        )

        entry = db.get(
            TimetableEntry,
            best_fix["entry_id"],
        )

        if entry is None:
            raise ValueError(
                "The timetable entry selected "
                "for this resolution no longer exists."
            )

        resolve_term_for_write(db, entry.term_id, allow_planning=True)

        validate_entry_state(
            entry,
            best_fix,
        )

        feasibility = (
            validate_destination(
                entry,
                best_fix,
                entries_before,
            )
        )

        clashes_before = (
            detect_clashes(
                entries_before
            )
        )

        move_from = best_fix[
            "move_from"
        ]

        move_to = best_fix[
            "move_to"
        ]

        old_day = entry.day
        old_start_time = entry.start_time
        old_end_time = entry.end_time

        entry.day = move_to[
            "day"
        ]

        entry.start_time = (
            move_to[
                "start_time"
            ]
        )

        entry.end_time = (
            move_to[
                "end_time"
            ]
        )

        db.flush()

        entries_after = (
            get_all_entries(
                db
            )
        )

        risks_after = build_enrollment_conflict_analysis(
            db,
            entries_after,
        )["risks"]

        clashes_after = (
            detect_clashes(
                entries_after
            )
        )

        risk_result = (
            validate_risk_improvement(
                entry_id=entry.id,
                risks_before=risks_before,
                risks_after=risks_after,
            )
        )

        compare_general_clashes(
            clashes_before,
            clashes_after,
        )

        history = (
            create_student_change_record(
                db,
                group_id=group_id,
                entry=entry,
                old_day=old_day,
                old_start_time=(
                    old_start_time
                ),
                old_end_time=(
                    old_end_time
                ),
                new_day=entry.day,
                new_start_time=(
                    entry.start_time
                ),
                new_end_time=(
                    entry.end_time
                ),
                score=float(
                    best_fix[
                        "score"
                    ]
                ),
                reasons=list(
                    best_fix.get(
                        "reasons",
                        [],
                    )
                ),
                risk_cost_before=(
                    risk_result[
                        "entry_cost_before"
                    ]
                ),
                risk_cost_after=(
                    risk_result[
                        "entry_cost_after"
                    ]
                ),
                total_risks_before=len(
                    risks_before
                ),
                total_risks_after=len(
                    risks_after
                ),
            )
        )

        db.flush()
        db.commit()

        db.refresh(entry)
        db.refresh(history)

        return {
            "success": True,
            "message": (
                "Student conflict resolution "
                "applied successfully."
            ),
            "change_id": history.id,
            "group_id": group_id,
            "applied_fix": {
                "entry_id": entry.id,
                "course_code": (
                    entry.course_code
                ),
                "course_name": (
                    entry.course_name
                ),
                "section": (
                    entry.section
                ),
                "faculty": (
                    entry.faculty
                ),
                "room": (
                    entry.room
                ),
                "move_from": {
                    "day": (
                        move_from[
                            "day"
                        ]
                    ),
                    "start_time": (
                        move_from[
                            "start_time"
                        ]
                    ),
                    "end_time": (
                        move_from[
                            "end_time"
                        ]
                    ),
                },
                "move_to": {
                    "day": entry.day,
                    "start_time": (
                        entry.start_time
                    ),
                    "end_time": (
                        entry.end_time
                    ),
                },
                "score": (
                    best_fix[
                        "score"
                    ]
                ),
                "faculty_available": (
                    feasibility[
                        "faculty_available"
                    ]
                ),
                "room_status": (
                    feasibility[
                        "room_status"
                    ]
                ),
                "room_available": (
                    feasibility[
                        "room_available"
                    ]
                ),
                "reasons": (
                    best_fix.get(
                        "reasons",
                        [],
                    )
                ),
            },
            "risk_validation": {
                "entry_risk_cost_before": (
                    risk_result[
                        "entry_cost_before"
                    ]
                ),
                "entry_risk_cost_after": (
                    risk_result[
                        "entry_cost_after"
                    ]
                ),
                "global_risk_cost_before": (
                    risk_result[
                        "total_cost_before"
                    ]
                ),
                "global_risk_cost_after": (
                    risk_result[
                        "total_cost_after"
                    ]
                ),
                "total_student_risks_before": len(
                    risks_before
                ),
                "total_student_risks_after": len(
                    risks_after
                ),
            },
            "general_clashes": {
                "before": len(
                    clashes_before
                ),
                "after": len(
                    clashes_after
                ),
            },
            "warning": (
                "The applied group used enrollment-backed conflict evidence."
                if group.get("enrollment_backed_edges", 0) > 0
                else
                "The applied group used explicitly inferred timetable evidence."
            ),
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# SAFE UNDO
# ---------------------------------------------------------------------------


def _transition_linked_report_after_undo(
    db: Session,
    *,
    change: StudentScheduleChange,
    actor_user_id: int | None,
) -> dict[str, Any] | None:
    if change.report_id is None:
        return None
    report = db.scalar(
        select(StudentClashReport)
        .where(StudentClashReport.id == change.report_id)
        .with_for_update()
    )
    if report is None:
        raise ValueError("The linked clash report no longer exists.")
    if report.status != "resolved":
        raise ValueError(
            "Undo rejected because the linked clash report is no longer resolved."
        )
    report.status = "under_review"
    report.resolution_note = None
    event = StudentClashReportEvent(
        report_id=report.id,
        actor_user_id=actor_user_id,
        action="resolution_undone",
        from_status="resolved",
        to_status="under_review",
        note="The applied timetable resolution was undone.",
    )
    db.add(event)
    db.flush()
    add_clash_report_status_notification(
        db,
        user_id=report.student_user_id,
        report_id=report.id,
        status="under_review",
        resolution_note="The previous resolution was undone for further review.",
        event_key=str(event.id),
        term_id=report.term_id,
    )
    return {"report_id": report.id, "report_status": report.status}


def _get_linked_report_redo_candidate(
    db: Session,
    *,
    change: StudentScheduleChange,
    entries: list[TimetableEntry],
) -> tuple[StudentClashReport, dict] | None:
    if change.report_id is None:
        return None
    report = db.scalar(
        select(StudentClashReport)
        .where(StudentClashReport.id == change.report_id)
        .with_for_update()
    )
    if report is None:
        raise ValueError("The linked clash report no longer exists.")
    if report.status != "under_review":
        raise ValueError(
            "Redo rejected because the linked clash report is not under review."
        )
    report_entry_ids = list(
        db.scalars(
            select(StudentClashReportItem.timetable_entry_id)
            .where(
                StudentClashReportItem.report_id == report.id,
                StudentClashReportItem.timetable_entry_id.is_not(None),
            )
            .order_by(StudentClashReportItem.id)
        ).all()
    )
    if len(set(report_entry_ids)) < 2:
        raise ValueError(
            "Redo rejected because the report no longer has enough timetable references."
        )
    result = generate_safe_candidates(
        db,
        entries=entries,
        target_entry_ids=[change.entry_id],
        report_entry_ids=report_entry_ids,
        limit=100,
        include_rejected_limit=0,
    )
    candidate = next(
        (
            item
            for item in result["candidates"]
            if item["candidate_id"] == change.candidate_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError(
            "Redo rejected because the original candidate is stale or no longer safe."
        )
    if candidate["status"] == "INSUFFICIENT_DATA":
        raise ValueError(
            "Redo rejected because required scheduling or enrollment data is missing."
        )
    if candidate["move_to"] != {
        "day": change.new_day,
        "start_time": change.new_start_time,
        "end_time": change.new_end_time,
    }:
        raise ValueError("Redo rejected because the stored destination no longer matches.")
    return report, candidate


def _transition_linked_report_after_redo(
    db: Session,
    *,
    change: StudentScheduleChange,
    linked: tuple[StudentClashReport, dict] | None,
    actor_user_id: int | None,
) -> dict[str, Any] | None:
    if linked is None:
        return None
    report, _candidate = linked
    if not change.report_resolution_note:
        raise ValueError("Redo rejected because the original resolution note is missing.")
    report.status = "resolved"
    report.resolution_note = change.report_resolution_note
    event = StudentClashReportEvent(
        report_id=report.id,
        actor_user_id=actor_user_id,
        action="resolution_redone",
        from_status="under_review",
        to_status="resolved",
        note=change.report_resolution_note,
    )
    db.add(event)
    db.flush()
    add_clash_report_status_notification(
        db,
        user_id=report.student_user_id,
        report_id=report.id,
        status="resolved",
        resolution_note=change.report_resolution_note,
        event_key=str(event.id),
        term_id=report.term_id,
    )
    return {"report_id": report.id, "report_status": report.status}


def undo_student_resolution(
    db: Session,
    *,
    change_id: int,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    try:
        change = db.get(
            StudentScheduleChange,
            change_id,
        )

        if change is None:
            raise ValueError(
                "Student schedule change record not found."
            )

        if change.undone:
            raise ValueError(
                "This student schedule change "
                "has already been undone."
            )

        entry = db.get(
            TimetableEntry,
            change.entry_id,
        )

        if entry is None:
            raise ValueError(
                "The timetable entry associated "
                "with this student schedule change "
                "no longer exists."
            )

        resolve_term_for_write(db, change.term_id, allow_planning=True)

        if (
            entry.day
            != change.new_day
            or entry.start_time
            != change.new_start_time
            or entry.end_time
            != change.new_end_time
        ):
            raise ValueError(
                "Undo rejected because the timetable "
                "entry has changed since this student "
                "resolution was applied."
            )

        entries_before = get_all_entries(
            db
        )

        risks_before = build_enrollment_conflict_analysis(
            db,
            entries_before,
        )["risks"]

        clashes_before = (
            detect_clashes(
                entries_before
            )
        )

        current_day = entry.day
        current_start = (
            entry.start_time
        )
        current_end = (
            entry.end_time
        )

        # Undo restores historical state even if that
        # historical state reintroduces conflicts.
        entry.day = change.old_day
        entry.start_time = (
            change.old_start_time
        )
        entry.end_time = (
            change.old_end_time
        )

        db.flush()

        entries_after = get_all_entries(
            db
        )

        risks_after = build_enrollment_conflict_analysis(
            db,
            entries_after,
        )["risks"]

        clashes_after = (
            detect_clashes(
                entries_after
            )
        )

        entry_risk_before = (
            calculate_entry_risk_cost(
                risks_before,
                entry.id,
            )
        )

        entry_risk_after = (
            calculate_entry_risk_cost(
                risks_after,
                entry.id,
            )
        )

        global_risk_before = (
            calculate_risk_cost(
                risks_before
            )
        )

        global_risk_after = (
            calculate_risk_cost(
                risks_after
            )
        )

        change.undone = True

        linked_report = _transition_linked_report_after_undo(
            db,
            change=change,
            actor_user_id=actor_user_id,
        )

        add_time_change_notifications(
            db,
            entry=entry,
            old_day=current_day,
            old_start_time=current_start,
            old_end_time=current_end,
            event_key=f"student-change-undo:{change.id}",
        )

        db.commit()

        db.refresh(entry)
        db.refresh(change)

        warnings: list[str] = []

        if (
            entry_risk_after
            > entry_risk_before
        ):
            warnings.append(
                "Undo restored the previous schedule "
                "but reintroduced student/cohort risk "
                "for this timetable entry."
            )

        if (
            global_risk_after
            > global_risk_before
        ):
            warnings.append(
                "Undo increased the global "
                "student/cohort risk score."
            )

        if (
            len(clashes_after)
            > len(clashes_before)
        ):
            warnings.append(
                "Undo reintroduced one or more "
                "general timetable clashes."
            )

        result = {
            "success": True,
            "message": (
                "Student schedule change "
                "undone successfully."
            ),
            "change_id": change.id,
            "entry_id": entry.id,
            "course_code": (
                entry.course_code
            ),
            "from": {
                "day": current_day,
                "start_time": (
                    current_start
                ),
                "end_time": (
                    current_end
                ),
            },
            "restored_to": {
                "day": entry.day,
                "start_time": (
                    entry.start_time
                ),
                "end_time": (
                    entry.end_time
                ),
            },
            "undone": change.undone,
            "risk_validation": {
                "entry_risk_cost_before": (
                    entry_risk_before
                ),
                "entry_risk_cost_after": (
                    entry_risk_after
                ),
                "global_risk_cost_before": (
                    global_risk_before
                ),
                "global_risk_cost_after": (
                    global_risk_after
                ),
                "total_student_risks_before": len(
                    risks_before
                ),
                "total_student_risks_after": len(
                    risks_after
                ),
            },
            "general_clashes": {
                "before": len(
                    clashes_before
                ),
                "after": len(
                    clashes_after
                ),
            },
            "warnings": warnings,
        }
        if linked_report is not None:
            result.update(linked_report)
        return result

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# SAFE REDO
# ---------------------------------------------------------------------------


def redo_student_resolution(
    db: Session,
    *,
    change_id: int,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    try:
        change = db.get(
            StudentScheduleChange,
            change_id,
        )

        if change is None:
            raise ValueError(
                "Student schedule change record not found."
            )

        if not change.undone:
            raise ValueError(
                "This student schedule change is already active."
            )

        entry = db.get(
            TimetableEntry,
            change.entry_id,
        )

        if entry is None:
            raise ValueError(
                "The timetable entry associated "
                "with this student schedule change "
                "no longer exists."
            )

        resolve_term_for_write(db, change.term_id, allow_planning=True)

        if (
            entry.day
            != change.old_day
            or entry.start_time
            != change.old_start_time
            or entry.end_time
            != change.old_end_time
        ):
            raise ValueError(
                "Redo rejected because the timetable "
                "entry changed after the resolution "
                "was undone."
            )

        entries_before = get_all_entries(
            db
        )

        linked_report_candidate = _get_linked_report_redo_candidate(
            db,
            change=change,
            entries=entries_before,
        )

        feasibility = (
            validate_specific_destination(
                entry,
                day=change.new_day,
                start_time=(
                    change.new_start_time
                ),
                end_time=(
                    change.new_end_time
                ),
                entries=entries_before,
            )
        )

        risks_before = build_enrollment_conflict_analysis(
            db,
            entries_before,
        )["risks"]

        clashes_before = (
            detect_clashes(
                entries_before
            )
        )

        old_day = entry.day
        old_start_time = (
            entry.start_time
        )
        old_end_time = (
            entry.end_time
        )

        entry.day = change.new_day
        entry.start_time = (
            change.new_start_time
        )
        entry.end_time = (
            change.new_end_time
        )

        db.flush()

        entries_after = get_all_entries(
            db
        )

        risks_after = build_enrollment_conflict_analysis(
            db,
            entries_after,
        )["risks"]

        clashes_after = (
            detect_clashes(
                entries_after
            )
        )

        risk_result = (
            validate_risk_improvement(
                entry_id=entry.id,
                risks_before=risks_before,
                risks_after=risks_after,
            )
        )

        compare_general_clashes(
            clashes_before,
            clashes_after,
        )

        change.undone = False

        linked_report = _transition_linked_report_after_redo(
            db,
            change=change,
            linked=linked_report_candidate,
            actor_user_id=actor_user_id,
        )

        add_time_change_notifications(
            db,
            entry=entry,
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
            event_key=f"student-change-redo:{change.id}",
        )

        db.commit()

        db.refresh(entry)
        db.refresh(change)

        result = {
            "success": True,
            "message": (
                "Student schedule change "
                "reapplied successfully."
            ),
            "change_id": change.id,
            "entry_id": entry.id,
            "course_code": (
                entry.course_code
            ),
            "from": {
                "day": old_day,
                "start_time": (
                    old_start_time
                ),
                "end_time": (
                    old_end_time
                ),
            },
            "reapplied_to": {
                "day": entry.day,
                "start_time": (
                    entry.start_time
                ),
                "end_time": (
                    entry.end_time
                ),
            },
            "undone": change.undone,
            "faculty_available": (
                feasibility[
                    "faculty_available"
                ]
            ),
            "room_status": (
                feasibility[
                    "room_status"
                ]
            ),
            "room_available": (
                feasibility[
                    "room_available"
                ]
            ),
            "risk_validation": {
                "entry_risk_cost_before": (
                    risk_result[
                        "entry_cost_before"
                    ]
                ),
                "entry_risk_cost_after": (
                    risk_result[
                        "entry_cost_after"
                    ]
                ),
                "global_risk_cost_before": (
                    risk_result[
                        "total_cost_before"
                    ]
                ),
                "global_risk_cost_after": (
                    risk_result[
                        "total_cost_after"
                    ]
                ),
                "total_student_risks_before": len(
                    risks_before
                ),
                "total_student_risks_after": len(
                    risks_after
                ),
            },
            "general_clashes": {
                "before": len(
                    clashes_before
                ),
                "after": len(
                    clashes_after
                ),
            },
            "reasons": parse_reasons(
                change
            ),
        }
        if linked_report is not None:
            result.update(linked_report)
        return result

    except Exception:
        db.rollback()
        raise
