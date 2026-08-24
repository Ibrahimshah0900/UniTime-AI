from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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
from backend.models import TimetableEntry
from backend.notification_service import add_time_change_notifications
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


# ---------------------------------------------------------------------------
# HISTORY MODEL
# ---------------------------------------------------------------------------


class StudentScheduleChange(Base):
    __tablename__ = "student_schedule_changes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_entries.id"),
        nullable=False,
        index=True,
    )

    group_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
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
) -> list[TimetableEntry]:
    statement = (
        select(TimetableEntry)
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
) -> dict:
    risks = analyze_student_conflicts(
        entries
    )

    groups = build_student_conflict_groups(
        risks
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
) -> tuple[dict, dict]:
    group = get_live_group(
        group_id,
        entries,
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

        group, best_fix = (
            get_live_best_fix(
                group_id,
                entries_before,
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

        risks_before = (
            analyze_student_conflicts(
                entries_before
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

        risks_after = (
            analyze_student_conflicts(
                entries_after
            )
        )

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
                "This change resolves an inferred "
                "student/cohort scheduling risk. "
                "It does not represent confirmed "
                "individual enrollment data."
            ),
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# SAFE UNDO
# ---------------------------------------------------------------------------


def undo_student_resolution(
    db: Session,
    *,
    change_id: int,
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

        risks_before = (
            analyze_student_conflicts(
                entries_before
            )
        )

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

        risks_after = (
            analyze_student_conflicts(
                entries_after
            )
        )

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

        return {
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

        risks_before = (
            analyze_student_conflicts(
                entries_before
            )
        )

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

        risks_after = (
            analyze_student_conflicts(
                entries_after
            )
        )

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

        return {
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

    except Exception:
        db.rollback()
        raise
