from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.models import TimetableChange, TimetableEntry
from backend.notification_service import add_time_change_notifications
from backend.schemas import TimetableTimeChangeRequest
from backend.student_conflict_analyzer import analyze_student_conflicts
from backend.student_resolution_applier import (
    calculate_risk_cost,
    validate_specific_destination,
)


def _all_entries(db: Session) -> list[TimetableEntry]:
    return list(db.scalars(select(TimetableEntry).order_by(TimetableEntry.id)).all())


def _entry_clashes(clashes: list[dict[str, Any]], entry_id: int) -> list[dict[str, Any]]:
    return [
        clash
        for clash in clashes
        if clash["entry_1"]["id"] == entry_id
        or clash["entry_2"]["id"] == entry_id
    ]


def _apply_safe_destination(
    db: Session,
    *,
    entry: TimetableEntry,
    day: str,
    start_time: str,
    end_time: str,
) -> dict[str, int]:
    entries_before = _all_entries(db)
    clashes_before = detect_clashes(entries_before)
    risks_before = analyze_student_conflicts(entries_before)

    try:
        validate_specific_destination(
            entry,
            day=day,
            start_time=start_time,
            end_time=end_time,
            entries=entries_before,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    entry.day = day
    entry.start_time = start_time
    entry.end_time = end_time
    db.flush()

    entries_after = _all_entries(db)
    clashes_after = detect_clashes(entries_after)
    risks_after = analyze_student_conflicts(entries_after)
    target_clashes = _entry_clashes(clashes_after, entry.id)
    risk_before = calculate_risk_cost(risks_before)
    risk_after = calculate_risk_cost(risks_after)

    if target_clashes:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The requested timetable slot creates a structural clash.",
                "clashes": target_clashes,
            },
        )
    if risk_after > risk_before:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The requested timetable slot increases student/cohort conflict risk.",
                "student_risk_cost_before": risk_before,
                "student_risk_cost_after": risk_after,
            },
        )

    return {
        "clashes_before": len(clashes_before),
        "clashes_after": len(clashes_after),
        "student_risk_cost_before": risk_before,
        "student_risk_cost_after": risk_after,
    }


def apply_manual_time_change(
    db: Session,
    *,
    entry_id: int,
    request: TimetableTimeChangeRequest,
) -> dict[str, Any]:
    try:
        entry = db.get(TimetableEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Timetable entry not found.")
        old_day = entry.day
        old_start_time = entry.start_time
        old_end_time = entry.end_time
        if (
            old_day == request.day
            and old_start_time == request.start_time
            and old_end_time == request.end_time
        ):
            raise HTTPException(status_code=409, detail="The requested timetable time is unchanged.")

        safety = _apply_safe_destination(
            db,
            entry=entry,
            day=request.day,
            start_time=request.start_time,
            end_time=request.end_time,
        )
        change = TimetableChange(
            entry_id=entry.id,
            change_type="manual_time_change",
            old_day=old_day,
            new_day=entry.day,
            old_start_time=old_start_time,
            new_start_time=entry.start_time,
            old_end_time=old_end_time,
            new_end_time=entry.end_time,
            reason="Manual timetable time change",
        )
        db.add(change)
        db.flush()
        add_time_change_notifications(
            db,
            entry=entry,
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
            event_key=f"manual-time-change:{change.id}",
        )
        db.commit()
        db.refresh(entry)
        db.refresh(change)
        return {"entry": entry, "change_id": change.id, "safety": safety}
    except Exception:
        db.rollback()
        raise


def undo_manual_time_change(db: Session, *, change_id: int) -> dict[str, Any]:
    try:
        change = db.get(TimetableChange, change_id)
        if change is None or change.change_type != "manual_time_change":
            raise HTTPException(status_code=404, detail="Manual time-change record not found.")
        if change.undone:
            raise HTTPException(status_code=409, detail="This change has already been undone.")
        entry = db.get(TimetableEntry, change.entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="The timetable entry no longer exists.")
        if (
            entry.day != change.new_day
            or entry.start_time != change.new_start_time
            or entry.end_time != change.new_end_time
        ):
            raise HTTPException(
                status_code=409,
                detail="Undo rejected because the timetable entry changed after this history record.",
            )

        old_day = entry.day
        old_start = entry.start_time
        old_end = entry.end_time
        clashes_before = detect_clashes(_all_entries(db))
        risks_before = analyze_student_conflicts(_all_entries(db))
        entry.day = change.old_day or entry.day
        entry.start_time = change.old_start_time or entry.start_time
        entry.end_time = change.old_end_time or entry.end_time
        change.undone = True
        db.flush()
        clashes_after = detect_clashes(_all_entries(db))
        risks_after = analyze_student_conflicts(_all_entries(db))
        add_time_change_notifications(
            db,
            entry=entry,
            old_day=old_day,
            old_start_time=old_start,
            old_end_time=old_end,
            event_key=f"manual-time-change-undo:{change.id}",
        )
        db.commit()
        db.refresh(entry)
        return {
            "success": True,
            "message": "Manual timetable time change undone successfully.",
            "change_id": change.id,
            "entry_id": entry.id,
            "from": {"day": old_day, "start_time": old_start, "end_time": old_end},
            "restored_to": {"day": entry.day, "start_time": entry.start_time, "end_time": entry.end_time},
            "undone": True,
            "clashes_before": len(clashes_before),
            "clashes_after": len(clashes_after),
            "student_risk_cost_before": calculate_risk_cost(risks_before),
            "student_risk_cost_after": calculate_risk_cost(risks_after),
        }
    except Exception:
        db.rollback()
        raise


def redo_manual_time_change(db: Session, *, change_id: int) -> dict[str, Any]:
    try:
        change = db.get(TimetableChange, change_id)
        if change is None or change.change_type != "manual_time_change":
            raise HTTPException(status_code=404, detail="Manual time-change record not found.")
        if not change.undone:
            raise HTTPException(status_code=409, detail="This change is already active.")
        entry = db.get(TimetableEntry, change.entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="The timetable entry no longer exists.")
        if (
            entry.day != change.old_day
            or entry.start_time != change.old_start_time
            or entry.end_time != change.old_end_time
        ):
            raise HTTPException(
                status_code=409,
                detail="Redo rejected because the timetable entry changed after the undo.",
            )

        old_day = entry.day
        old_start = entry.start_time
        old_end = entry.end_time
        safety = _apply_safe_destination(
            db,
            entry=entry,
            day=change.new_day or entry.day,
            start_time=change.new_start_time or entry.start_time,
            end_time=change.new_end_time or entry.end_time,
        )
        change.undone = False
        add_time_change_notifications(
            db,
            entry=entry,
            old_day=old_day,
            old_start_time=old_start,
            old_end_time=old_end,
            event_key=f"manual-time-change-redo:{change.id}",
        )
        db.commit()
        db.refresh(entry)
        return {
            "success": True,
            "message": "Manual timetable time change reapplied successfully.",
            "change_id": change.id,
            "entry_id": entry.id,
            "from": {"day": old_day, "start_time": old_start, "end_time": old_end},
            "reapplied_to": {"day": entry.day, "start_time": entry.start_time, "end_time": entry.end_time},
            "undone": False,
            "safety": safety,
        }
    except Exception:
        db.rollback()
        raise
