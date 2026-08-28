from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.institutional_constraints import (
    InstitutionalConstraintContext,
    build_institutional_constraint_context,
    component_identity,
    subject_identity,
    validate_institutional_destination,
)
from backend.models import AcademicTerm, CourseOffering, TimetableEntry
from backend.scheduling_policy import (
    DEFAULT_SCHEDULING_POLICY,
    INSTITUTIONAL_POLICY_VERSION,
    allowed_days_for,
    time_to_minutes,
)
from backend.term_service import get_term


DAY_ORDER = {
    day: index
    for index, day in enumerate(DEFAULT_SCHEDULING_POLICY.operating_days)
}


def _planning_term(db: Session, term_id: int) -> AcademicTerm:
    term = get_term(db, term_id)
    if term.status != "planning":
        raise HTTPException(
            status_code=409,
            detail=(
                "Automatic timetable generation is only allowed for "
                "a planning academic term."
            ),
        )
    return term


def _all_entries(db: Session, term_id: int) -> list[TimetableEntry]:
    return list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == term_id)
            .order_by(TimetableEntry.id)
        ).all()
    )


def _duration_minutes(entry) -> int:
    return time_to_minutes(entry.end_time) - time_to_minutes(entry.start_time)


def _preview_id(
    *,
    term_id: int,
    context: InstitutionalConstraintContext,
    entries: list[TimetableEntry],
) -> str:
    state = {
        "term_id": term_id,
        "policy_version": INSTITUTIONAL_POLICY_VERSION,
        "institutional_context": context.fingerprint,
        "timetable": [
            [
                entry.id,
                entry.entry_kind,
                entry.course_code,
                entry.course_name,
                entry.semester,
                entry.section,
                entry.faculty,
                entry.room,
                entry.day,
                entry.start_time,
                entry.end_time,
                entry.class_type,
                entry.source,
            ]
            for entry in entries
        ],
    }
    return hashlib.sha256(
        json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _matching_existing_entries(
    entries: list[TimetableEntry],
    offering: CourseOffering,
) -> list[TimetableEntry]:
    target = component_identity(
        offering.course_code,
        offering.semester,
        offering.section,
        offering.class_type,
    )
    return [
        entry
        for entry in entries
        if component_identity(
            entry.course_code,
            entry.semester,
            entry.section,
            entry.class_type,
        )
        == target
    ]


def _aligned_start(value: int) -> int:
    policy = DEFAULT_SCHEDULING_POLICY
    opening = time_to_minutes(policy.opens_at)
    interval = policy.slot_interval_minutes
    if value <= opening:
        return opening
    offset = value - opening
    steps = (offset + interval - 1) // interval
    return opening + steps * interval


def _candidate_slots(
    context: InstitutionalConstraintContext,
    *,
    faculty_user_id: int,
    day: str,
    duration_minutes: int,
) -> list[dict[str, str]]:
    from backend.scheduling_policy import minutes_to_time

    windows = context.availability_by_faculty.get(
        faculty_user_id,
        (),
    )
    candidates: set[tuple[str, str, str]] = set()
    policy = DEFAULT_SCHEDULING_POLICY
    for window in windows:
        if window.day != day:
            continue
        start = _aligned_start(time_to_minutes(window.start_time))
        end_limit = time_to_minutes(window.end_time)
        while start + duration_minutes <= end_limit:
            end = start + duration_minutes
            slot = {
                "day": day,
                "start_time": minutes_to_time(start),
                "end_time": minutes_to_time(end),
            }
            if not policy.validate_slot(**slot):
                candidates.add(
                    (
                        slot["day"],
                        slot["start_time"],
                        slot["end_time"],
                    )
                )
            start += policy.slot_interval_minutes
    return [
        {
            "day": day_value,
            "start_time": start,
            "end_time": end,
        }
        for day_value, start, end in sorted(
            candidates,
            key=lambda item: (
                DAY_ORDER.get(item[0], 99),
                item[1],
                item[2],
            ),
        )
    ]


def _proposal_namespace(
    *,
    synthetic_id: int,
    term_id: int,
    offering: CourseOffering,
    faculty_name: str,
    slot: dict[str, str],
):
    return SimpleNamespace(
        id=synthetic_id,
        term_id=term_id,
        entry_kind="course",
        course_code=offering.course_code,
        course_name=offering.course_name,
        semester=str(offering.semester),
        section=offering.section,
        faculty=faculty_name,
        room=offering.room,
        day=slot["day"],
        start_time=slot["start_time"],
        end_time=slot["end_time"],
        class_type=offering.class_type,
        raw_text=f"Generated from course offering {offering.id}",
        source="generated",
    )


def preview_timetable_generation(
    db: Session,
    *,
    term_id: int,
) -> dict:
    _planning_term(db, term_id)
    entries = _all_entries(db, term_id)
    context = build_institutional_constraint_context(
        db,
        term_id=term_id,
    )
    offerings = sorted(
        context.offerings_by_component.values(),
        key=lambda item: (
            item.semester,
            item.course_code,
            item.section,
            0 if item.class_type == "lecture" else 1,
            item.id,
        ),
    )
    preview_id = _preview_id(
        term_id=term_id,
        context=context,
        entries=entries,
    )

    readiness_errors: list[str] = []
    unscheduled: list[str] = []
    satisfied_ids: list[int] = []
    tasks: list[dict] = []

    if not offerings:
        readiness_errors.append(
            "No course offerings exist for this planning term."
        )

    baseline_clashes = detect_clashes(entries)
    if baseline_clashes:
        readiness_errors.append(
            "Existing planning-term timetable entries already contain "
            f"{len(baseline_clashes)} structural clash(es). Resolve them "
            "before automatic generation."
        )

    seen_subjects: set[tuple[str, int, str]] = set()
    subject_assignment: dict[
        tuple[str, int, str],
        tuple[int, str, str],
    ] = {}

    for offering in offerings:
        subject = subject_identity(
            offering.course_code,
            offering.semester,
            offering.section,
        )
        if subject is None:
            readiness_errors.append(
                f"Offering {offering.id} has invalid scheduling identity."
            )
            continue

        assignments = context.assignments_by_subject.get(
            subject,
            (),
        )
        if subject not in seen_subjects:
            seen_subjects.add(subject)
            if len(assignments) == 0:
                readiness_errors.append(
                    f"{offering.course_code} semester {offering.semester} "
                    f"section {offering.section} has no faculty allocation."
                )
            elif len(assignments) > 1:
                readiness_errors.append(
                    f"{offering.course_code} semester {offering.semester} "
                    f"section {offering.section} has multiple faculty allocations."
                )
            else:
                faculty = context.faculty_by_id.get(
                    assignments[0].faculty_user_id
                )
                if (
                    faculty is None
                    or faculty.role != "faculty"
                    or not faculty.is_active
                    or not faculty.email
                ):
                    readiness_errors.append(
                        f"{offering.course_code} semester {offering.semester} "
                        f"section {offering.section} does not resolve to one "
                        "active faculty account."
                    )
                else:
                    subject_assignment[subject] = (
                        faculty.id,
                        faculty.full_name,
                        faculty.email,
                    )

        assigned = subject_assignment.get(subject)
        required_days = allowed_days_for(
            offering.semester,
            offering.class_type,
        )

        if not offering.room or not offering.room.strip():
            readiness_errors.append(
                f"Offering {offering.id} ({offering.course_code} "
                f"{offering.class_type}) requires a room or Online assignment."
            )

        if assigned is not None:
            faculty_id, _faculty_name, _faculty_email = assigned
            windows = context.availability_by_faculty.get(
                faculty_id,
                (),
            )
            for day in required_days:
                if not any(window.day == day for window in windows):
                    readiness_errors.append(
                        f"Faculty for {offering.course_code} has no declared "
                        f"availability on required day {day}."
                    )

        existing = _matching_existing_entries(
            entries,
            offering,
        )
        existing_by_day: dict[str, list[TimetableEntry]] = {}
        for entry in existing:
            existing_by_day.setdefault(entry.day, []).append(entry)
            if entry.day not in required_days:
                readiness_errors.append(
                    f"Existing entry {entry.id} for {offering.course_code} "
                    f"{offering.class_type} is on disallowed day {entry.day}."
                )
            if _duration_minutes(entry) != offering.duration_minutes:
                readiness_errors.append(
                    f"Existing entry {entry.id} duration does not match "
                    f"course offering {offering.id}."
                )
            if assigned is not None:
                _faculty_id, faculty_name, faculty_email = assigned
                display = (entry.faculty or "").strip().lower()
                if display not in {
                    faculty_name.strip().lower(),
                    faculty_email.strip().lower(),
                }:
                    readiness_errors.append(
                        f"Existing entry {entry.id} does not identify the "
                        "allocated faculty member."
                    )
            if (
                offering.room
                and (entry.room or "").strip().lower()
                != offering.room.strip().lower()
            ):
                readiness_errors.append(
                    f"Existing entry {entry.id} room does not match "
                    f"course offering {offering.id}."
                )

        for day in required_days:
            day_entries = existing_by_day.get(day, [])
            if len(day_entries) > 1:
                readiness_errors.append(
                    f"Offering {offering.id} has duplicate timetable "
                    f"sessions on {day}."
                )
                continue
            if len(day_entries) == 1:
                satisfied_ids.append(day_entries[0].id)
                continue

            if (
                assigned is None
                or not offering.room
                or not offering.room.strip()
            ):
                continue
            faculty_id, faculty_name, _faculty_email = assigned
            candidates = _candidate_slots(
                context,
                faculty_user_id=faculty_id,
                day=day,
                duration_minutes=offering.duration_minutes,
            )
            if not candidates:
                unscheduled.append(
                    f"{offering.course_code} semester {offering.semester} "
                    f"section {offering.section} {offering.class_type} "
                    f"has no candidate slot on {day} inside faculty availability."
                )
                continue
            tasks.append(
                {
                    "offering": offering,
                    "faculty_user_id": faculty_id,
                    "faculty_name": faculty_name,
                    "day": day,
                    "candidate_slots": candidates,
                }
            )

    tasks.sort(
        key=lambda item: (
            len(item["candidate_slots"]),
            item["offering"].semester,
            DAY_ORDER.get(item["day"], 99),
            item["offering"].course_code,
            item["offering"].section,
            0 if item["offering"].class_type == "lecture" else 1,
            item["offering"].id,
        )
    )

    working_entries: list = list(entries)
    proposals: list[dict] = []
    synthetic_id = -1
    for task in tasks:
        offering = task["offering"]
        chosen: dict[str, str] | None = None
        for slot in task["candidate_slots"]:
            candidate_entry = _proposal_namespace(
                synthetic_id=synthetic_id,
                term_id=term_id,
                offering=offering,
                faculty_name=task["faculty_name"],
                slot=slot,
            )
            validation = validate_institutional_destination(
                context,
                candidate_entry,
                day=slot["day"],
                start_time=slot["start_time"],
                end_time=slot["end_time"],
                entries=working_entries,
                strict_managed=True,
            )
            if validation["hard_failures"]:
                continue
            chosen = slot
            working_entries.append(candidate_entry)
            synthetic_id -= 1
            proposals.append(
                {
                    "offering_id": offering.id,
                    "faculty_user_id": task["faculty_user_id"],
                    "faculty_name": task["faculty_name"],
                    "course_code": offering.course_code,
                    "course_name": offering.course_name,
                    "semester": offering.semester,
                    "section": offering.section,
                    "class_type": offering.class_type,
                    "room": offering.room,
                    "day": slot["day"],
                    "start_time": slot["start_time"],
                    "end_time": slot["end_time"],
                    "duration_minutes": offering.duration_minutes,
                }
            )
            break
        if chosen is None:
            unscheduled.append(
                f"{offering.course_code} semester {offering.semester} "
                f"section {offering.section} {offering.class_type} "
                f"could not be placed on {task['day']} without violating "
                "semester, faculty, room, availability, or operating-time constraints."
            )

    readiness_errors = list(dict.fromkeys(readiness_errors))
    unscheduled = list(dict.fromkeys(unscheduled))
    satisfied_ids = sorted(set(satisfied_ids))
    proposals.sort(
        key=lambda item: (
            item["semester"],
            DAY_ORDER.get(item["day"], 99),
            item["start_time"],
            item["course_code"],
            item["section"],
            0 if item["class_type"] == "lecture" else 1,
            item["offering_id"],
        )
    )
    complete = not readiness_errors and not unscheduled

    return {
        "term_id": term_id,
        "status": "READY" if complete else "BLOCKED",
        "preview_id": preview_id,
        "complete": complete,
        "existing_satisfied_entry_ids": satisfied_ids,
        "existing_satisfied_count": len(satisfied_ids),
        "proposed_count": len(proposals),
        "readiness_errors": readiness_errors,
        "unscheduled": unscheduled,
        "proposals": proposals,
        "policy_note": (
            "Generation is deterministic. Semesters 1,3,5,7 use "
            "Monday/Wednesday lectures and Thursday labs; semesters "
            "2,4,6,8 use Tuesday/Thursday lectures and Friday labs. "
            "Same-semester, faculty, physical-room, operating-time, and "
            "declared faculty-availability constraints are hard filters."
        ),
    }


def apply_timetable_generation(
    db: Session,
    *,
    term_id: int,
    preview_id: str,
) -> dict:
    try:
        _planning_term(db, term_id)
        live_preview = preview_timetable_generation(
            db,
            term_id=term_id,
        )
        if live_preview["preview_id"] != preview_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Timetable generation preview is stale. Generate a fresh "
                    "preview from the current planning data."
                ),
            )
        if not live_preview["complete"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Planning data is not ready for timetable generation.",
                    "readiness_errors": live_preview["readiness_errors"],
                    "unscheduled": live_preview["unscheduled"],
                },
            )

        created: list[TimetableEntry] = []
        for proposal in live_preview["proposals"]:
            entry = TimetableEntry(
                term_id=term_id,
                entry_kind="course",
                course_code=proposal["course_code"],
                course_name=proposal["course_name"],
                semester=str(proposal["semester"]),
                section=proposal["section"],
                faculty=proposal["faculty_name"],
                room=proposal["room"],
                day=proposal["day"],
                start_time=proposal["start_time"],
                end_time=proposal["end_time"],
                class_type=proposal["class_type"],
                raw_text=(
                    "Generated from course offering "
                    f"{proposal['offering_id']}"
                ),
                source="generated",
            )
            db.add(entry)
            created.append(entry)

        db.flush()

        entries_after = _all_entries(db, term_id)
        clashes_after = detect_clashes(entries_after)
        if clashes_after:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Live validation detected a structural clash. "
                        "No generated timetable entries were committed."
                    ),
                    "clashes": clashes_after,
                },
            )

        db.commit()
        for entry in created:
            db.refresh(entry)

        return {
            "success": True,
            "term_id": term_id,
            "preview_id": preview_id,
            "created_count": len(created),
            "existing_satisfied_count": live_preview[
                "existing_satisfied_count"
            ],
            "entries": created,
            "message": (
                "Timetable generation applied successfully."
                if created
                else "Planning timetable already satisfies all configured offerings."
            ),
        }
    except Exception:
        db.rollback()
        raise
