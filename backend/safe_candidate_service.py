from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.clash_detector import detect_clashes
from backend.enrollment_conflict_graph import (
    build_enrollment_conflict_analysis,
    build_enrollment_conflict_evidence,
)
from backend.global_optimizer import clone_entries
from backend.models import TimetableEntry
from backend.scheduling_policy import (
    DEFAULT_RANKING_WEIGHTS,
    DEFAULT_SCHEDULING_POLICY,
    RankingWeights,
    SchedulingPolicy,
    time_to_minutes,
)
from backend.student_conflict_groups import build_student_conflict_groups


RISK_WEIGHTS = {"confirmed": 100, "probable": 10, "possible": 2}
STATUS_PRIORITY = {
    "SAFE": 0,
    "CONDITIONALLY_SAFE": 1,
    "INSUFFICIENT_DATA": 2,
    "REJECTED": 3,
}


def calculate_weighted_risk_cost(risks: list[dict]) -> int:
    return sum(
        RISK_WEIGHTS.get(risk["risk_level"], 0)
        * (
            max(int(risk.get("affected_student_count", 0)), 1)
            if risk["risk_level"] == "confirmed"
            else 1
        )
        for risk in risks
    )


def _confirmed_pairs(risks: list[dict]) -> set[tuple[int, int]]:
    return {
        tuple(sorted((risk["entry_1"]["id"], risk["entry_2"]["id"])))
        for risk in risks
        if risk["risk_level"] == "confirmed"
    }


def _entry_clashes(clashes: list[dict], entry_id: int) -> list[dict]:
    return [
        clash
        for clash in clashes
        if entry_id in {clash["entry_1"]["id"], clash["entry_2"]["id"]}
    ]


def _overlap_remains(entries: list, report_entry_ids: set[int]) -> bool:
    selected = [entry for entry in entries if entry.id in report_entry_ids]
    for index, first in enumerate(selected):
        for second in selected[index + 1 :]:
            if (
                first.day == second.day
                and first.start_time < second.end_time
                and second.start_time < first.end_time
            ):
                return True
    return False


def _analysis_fingerprint(analysis: dict) -> dict:
    return {
        "term_id": analysis["coverage"]["term_id"],
        "entry_enrollment_counts": sorted(
            analysis["coverage"].get("entry_enrollment_counts", {}).items()
        ),
        "unmapped_enrollment_records": analysis["coverage"][
            "unmapped_enrollment_records"
        ],
        "risks": [
            [
                risk["entry_1"]["id"],
                risk["entry_2"]["id"],
                risk["risk_level"],
                risk.get("affected_student_count", 0),
                risk.get("evidence_source"),
            ]
            for risk in analysis["risks"]
        ],
    }


def _policy_fingerprint(policy: SchedulingPolicy) -> dict:
    return {
        "operating_days": policy.operating_days,
        "opens_at": policy.opens_at,
        "closes_at": policy.closes_at,
        "slot_interval_minutes": policy.slot_interval_minutes,
        "minimum_duration_minutes": policy.minimum_duration_minutes,
        "maximum_duration_minutes": policy.maximum_duration_minutes,
        "blocked_periods": [
            [period.day, period.start_time, period.end_time, period.reason]
            for period in policy.blocked_periods
        ],
    }


def _candidate_id(
    target: TimetableEntry,
    slot: dict[str, str],
    entries: list,
    *,
    analysis: dict,
    policy: SchedulingPolicy,
) -> str:
    state = {
        "entry_id": target.id,
        "from": [target.day, target.start_time, target.end_time],
        "to": [slot["day"], slot["start_time"], slot["end_time"]],
        "timetable": [
            [
                entry.id,
                entry.term_id,
                entry.entry_kind,
                entry.course_code,
                entry.semester,
                entry.section,
                entry.class_type,
                entry.day,
                entry.start_time,
                entry.end_time,
                entry.room,
                entry.faculty,
            ]
            for entry in sorted(entries, key=lambda item: item.id)
        ],
        "enrollment_analysis": _analysis_fingerprint(analysis),
        "policy": _policy_fingerprint(policy),
    }
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def _simulate(entries: list, target_id: int, slot: dict[str, str]) -> list:
    simulated = clone_entries(entries)
    target = next((entry for entry in simulated if entry.id == target_id), None)
    if target is None:
        raise ValueError("Candidate target is missing from the timetable simulation.")
    target.day = slot["day"]
    target.start_time = slot["start_time"]
    target.end_time = slot["end_time"]
    return simulated


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _score_candidate(
    *,
    target: TimetableEntry,
    slot: dict[str, str],
    status: str,
    affected_students: int,
    confirmed_removed: int,
    inferred_removed: int,
    clashes_removed: int,
    groups_removed: int,
    policy: SchedulingPolicy,
    weights: RankingWeights,
) -> tuple[int, list[dict]]:
    components: list[dict] = []

    def add(signal: str, value: int, explanation: str) -> None:
        components.append(
            {"signal": signal, "value": value, "explanation": explanation}
        )

    add(
        "confirmed_conflicts_removed",
        confirmed_removed * weights.confirmed_conflict_removed,
        f"Removes {confirmed_removed} confirmed enrollment-backed conflict(s).",
    )
    add(
        "inferred_conflicts_removed",
        inferred_removed * weights.inferred_conflict_removed,
        f"Removes {inferred_removed} inferred conflict signal(s).",
    )
    add(
        "structural_clashes_removed",
        clashes_removed * weights.structural_clash_removed,
        f"Removes {clashes_removed} structural clash(es).",
    )
    add(
        "conflict_groups_removed",
        groups_removed * weights.conflict_group_removed,
        f"Reduces conflict groups by {groups_removed}.",
    )
    add(
        "affected_students",
        -affected_students * weights.affected_student_penalty,
        f"Moving the offering affects {affected_students} enrolled student(s).",
    )
    day_order = {day: index for index, day in enumerate(policy.operating_days)}
    day_distance = abs(day_order.get(target.day, 0) - day_order.get(slot["day"], 0))
    add(
        "day_distance",
        -day_distance * weights.day_distance_penalty,
        f"Moves the class {day_distance} operating day step(s).",
    )
    shift_units = abs(
        time_to_minutes(target.start_time) - time_to_minutes(slot["start_time"])
    ) // 30
    add(
        "time_shift",
        -shift_units * weights.half_hour_shift_penalty,
        f"Shifts the start time by {shift_units * 30} minute(s).",
    )
    if time_to_minutes(slot["start_time"]) >= 17 * 60:
        add(
            "late_slot",
            -weights.late_slot_penalty,
            "Destination begins at or after 17:00.",
        )
    if status == "CONDITIONALLY_SAFE":
        add(
            "missing_optional_metadata",
            -weights.conditional_data_penalty,
            "Important scheduling metadata still requires coordinator confirmation.",
        )
    elif status == "INSUFFICIENT_DATA":
        add(
            "insufficient_data",
            -weights.insufficient_data_penalty,
            "Required assignment data is missing.",
        )
    raw_score = 50 + sum(component["value"] for component in components)
    return max(0, min(raw_score, 100)), components


def generate_safe_candidates(
    db: Session,
    *,
    entries: list[TimetableEntry],
    target_entry_ids: list[int],
    report_entry_ids: list[int] | None = None,
    policy: SchedulingPolicy = DEFAULT_SCHEDULING_POLICY,
    weights: RankingWeights = DEFAULT_RANKING_WEIGHTS,
    limit: int = 20,
    include_rejected_limit: int = 20,
) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Candidate limit must be between 1 and 100.")
    if include_rejected_limit < 0 or include_rejected_limit > 100:
        raise HTTPException(
            status_code=422,
            detail="Rejected-candidate limit must be between 0 and 100.",
        )
    entry_lookup = {entry.id: entry for entry in entries}
    targets = []
    for entry_id in dict.fromkeys(target_entry_ids):
        entry = entry_lookup.get(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Timetable entry {entry_id} was not found.")
        targets.append(entry)
    if not targets:
        raise HTTPException(status_code=422, detail="At least one target entry is required.")

    enrollment_evidence = build_enrollment_conflict_evidence(db, entries)
    baseline_analysis = build_enrollment_conflict_analysis(
        db,
        entries,
        evidence=enrollment_evidence,
    )
    baseline_risks = baseline_analysis["risks"]
    baseline_clashes = detect_clashes(entries)
    baseline_groups = build_student_conflict_groups(baseline_risks)
    baseline_confirmed = _confirmed_pairs(baseline_risks)
    baseline_risk_cost = calculate_weighted_risk_cost(baseline_risks)
    entry_counts = baseline_analysis["coverage"].get("entry_enrollment_counts", {})
    required_report_ids = set(report_entry_ids or [])
    missing_report_ids = required_report_ids - entry_lookup.keys()
    if missing_report_ids:
        missing_text = ", ".join(str(entry_id) for entry_id in sorted(missing_report_ids))
        raise HTTPException(
            status_code=404,
            detail=f"Reported timetable entry or entries were not found: {missing_text}.",
        )
    if report_entry_ids is not None and len(required_report_ids) < 2:
        raise HTTPException(
            status_code=422,
            detail="A report resolution requires at least two distinct timetable entries.",
        )

    accepted: list[dict] = []
    rejected: list[dict] = []
    generated = 0
    for target in targets:
        duration = time_to_minutes(target.end_time) - time_to_minutes(target.start_time)
        for slot in policy.generate_slots(
            duration_minutes=duration,
            include_blocked=True,
        ):
            if (
                slot["day"] == target.day
                and slot["start_time"] == target.start_time
                and slot["end_time"] == target.end_time
            ):
                continue
            generated += 1
            candidate_id = _candidate_id(
                target,
                slot,
                entries,
                analysis=baseline_analysis,
                policy=policy,
            )
            checks: list[dict] = []
            failures = policy.validate_slot(**slot)
            if failures:
                rejected.append(
                    {
                        "candidate_id": candidate_id,
                        "entry_id": target.id,
                        "move_to": slot,
                        "status": "REJECTED",
                        "rejection_reasons": failures,
                    }
                )
                continue

            simulated = _simulate(entries, target.id, slot)
            after_analysis = build_enrollment_conflict_analysis(
                db,
                simulated,
                evidence=enrollment_evidence,
            )
            after_risks = after_analysis["risks"]
            after_clashes = detect_clashes(simulated)
            after_groups = build_student_conflict_groups(after_risks)
            after_confirmed = _confirmed_pairs(after_risks)
            new_confirmed = after_confirmed - baseline_confirmed
            target_clashes = _entry_clashes(after_clashes, target.id)
            report_overlap_remains = bool(
                required_report_ids
                and _overlap_remains(simulated, required_report_ids)
            )
            hard_failures: list[str] = []
            if target_clashes:
                clash_types = sorted({clash["type"] for clash in target_clashes})
                hard_failures.append(
                    "Destination creates target structural clash(es): " + ", ".join(clash_types) + "."
                )
            if len(after_clashes) > len(baseline_clashes):
                hard_failures.append("General structural clash count increases.")
            if new_confirmed:
                hard_failures.append("Destination creates a new confirmed student conflict.")
            if len(after_groups) > len(baseline_groups):
                hard_failures.append("Student conflict group count increases.")
            if calculate_weighted_risk_cost(after_risks) > baseline_risk_cost:
                hard_failures.append("Global weighted student-conflict risk increases.")
            if report_overlap_remains:
                hard_failures.append("The original reported overlap remains.")

            checks.extend(
                [
                    _check(
                        "institutional_policy",
                        "PASS" if not failures else "FAIL",
                        "Destination obeys operating-day, operating-hour, duration, and blocked-period policy.",
                    ),
                    _check(
                        "structural_clashes",
                        "PASS" if not target_clashes and len(after_clashes) <= len(baseline_clashes) else "FAIL",
                        f"Structural clashes: {len(baseline_clashes)} before, {len(after_clashes)} after.",
                    ),
                    _check(
                        "confirmed_student_conflicts",
                        "PASS" if not new_confirmed else "FAIL",
                        f"Confirmed conflicts: {len(baseline_confirmed)} before, {len(after_confirmed)} after; new={len(new_confirmed)}.",
                    ),
                    _check(
                        "conflict_groups",
                        "PASS" if len(after_groups) <= len(baseline_groups) else "FAIL",
                        f"Conflict groups: {len(baseline_groups)} before, {len(after_groups)} after.",
                    ),
                ]
            )
            if required_report_ids:
                checks.append(
                    _check(
                        "original_report_overlap",
                        "PASS" if not report_overlap_remains else "FAIL",
                        "The selected report entries no longer overlap." if not report_overlap_remains else "The selected report entries still overlap.",
                    )
                )
            if hard_failures:
                rejected.append(
                    {
                        "candidate_id": candidate_id,
                        "entry_id": target.id,
                        "move_to": slot,
                        "status": "REJECTED",
                        "rejection_reasons": hard_failures,
                        "checks": checks,
                    }
                )
                continue

            missing_data: list[str] = []
            insufficient_data = False
            room_value = (target.room or "").strip().lower()
            faculty_value = (target.faculty or "").strip().lower()
            if not room_value and room_value != "online":
                missing_data.append("No room is assigned to the offering.")
                insufficient_data = True
            elif room_value != "online":
                missing_data.append("Room capacity/type/equipment metadata is not modeled.")
            if not faculty_value or faculty_value == "tba":
                missing_data.append("Faculty identity and hard availability metadata are unavailable.")
                insufficient_data = True
            else:
                missing_data.append("Faculty hard-unavailability calendar is not modeled.")
            if int(entry_counts.get(target.id, 0)) == 0:
                missing_data.append(
                    "No verified active enrollment coverage is available for the target offering."
                )
                insufficient_data = True
            simulated_target = next(entry for entry in simulated if entry.id == target.id)
            uncovered_overlaps = sorted(
                entry.id
                for entry in simulated
                if entry.id != target.id
                and getattr(entry, "entry_kind", "course") == "course"
                and simulated_target.day == entry.day
                and simulated_target.start_time < entry.end_time
                and entry.start_time < simulated_target.end_time
                and int(entry_counts.get(entry.id, 0)) == 0
            )
            if uncovered_overlaps:
                missing_data.append(
                    "Destination overlaps offering(s) without verified enrollment coverage: "
                    + ", ".join(str(entry_id) for entry_id in uncovered_overlaps)
                    + "."
                )
                insufficient_data = True
            status = (
                "INSUFFICIENT_DATA"
                if insufficient_data
                else "CONDITIONALLY_SAFE"
                if missing_data
                else "SAFE"
            )
            checks.append(
                _check(
                    "metadata_completeness",
                    "WARN" if missing_data else "PASS",
                    " ".join(missing_data) if missing_data else "All configured metadata checks passed.",
                )
            )
            confirmed_removed = len(baseline_confirmed - after_confirmed)
            inferred_before = sum(1 for risk in baseline_risks if risk["risk_level"] != "confirmed")
            inferred_after = sum(1 for risk in after_risks if risk["risk_level"] != "confirmed")
            score, score_components = _score_candidate(
                target=target,
                slot=slot,
                status=status,
                affected_students=int(entry_counts.get(target.id, 0)),
                confirmed_removed=confirmed_removed,
                inferred_removed=max(inferred_before - inferred_after, 0),
                clashes_removed=max(len(baseline_clashes) - len(after_clashes), 0),
                groups_removed=max(len(baseline_groups) - len(after_groups), 0),
                policy=policy,
                weights=weights,
            )
            accepted.append(
                {
                    "candidate_id": candidate_id,
                    "status": status,
                    "actionable_without_confirmation": status == "SAFE",
                    "entry_id": target.id,
                    "course_code": target.course_code,
                    "course_name": target.course_name,
                    "section": target.section,
                    "move_from": {
                        "day": target.day,
                        "start_time": target.start_time,
                        "end_time": target.end_time,
                    },
                    "move_to": slot,
                    "duration_minutes": duration,
                    "rank_score": score,
                    "score_components": score_components,
                    "checks": checks,
                    "missing_data": missing_data,
                    "rejection_reasons": [],
                    "impact": {
                        "affected_students": int(entry_counts.get(target.id, 0)),
                        "confirmed_conflicts_before": len(baseline_confirmed),
                        "confirmed_conflicts_after": len(after_confirmed),
                        "confirmed_conflicts_removed": confirmed_removed,
                        "new_confirmed_conflicts": len(new_confirmed),
                        "student_risks_before": len(baseline_risks),
                        "student_risks_after": len(after_risks),
                        "structural_clashes_before": len(baseline_clashes),
                        "structural_clashes_after": len(after_clashes),
                        "conflict_groups_before": len(baseline_groups),
                        "conflict_groups_after": len(after_groups),
                        "weighted_risk_before": baseline_risk_cost,
                        "weighted_risk_after": calculate_weighted_risk_cost(after_risks),
                        "timetable_entries_changed": 1,
                    },
                }
            )

    day_order = {day: index for index, day in enumerate(policy.operating_days)}
    accepted.sort(
        key=lambda item: (
            STATUS_PRIORITY[item["status"]],
            -item["rank_score"],
            -item["impact"]["confirmed_conflicts_removed"],
            item["impact"]["affected_students"],
            day_order[item["move_to"]["day"]],
            item["move_to"]["start_time"],
            item["entry_id"],
        )
    )
    return {
        "policy": {
            "operating_days": list(policy.operating_days),
            "opens_at": policy.opens_at,
            "closes_at": policy.closes_at,
            "slot_interval_minutes": policy.slot_interval_minutes,
            "blocked_periods": [
                {
                    "day": period.day,
                    "start_time": period.start_time,
                    "end_time": period.end_time,
                    "reason": period.reason,
                }
                for period in policy.blocked_periods
            ],
        },
        "summary": {
            "generated": generated,
            "safe": sum(1 for item in accepted if item["status"] == "SAFE"),
            "conditionally_safe": sum(1 for item in accepted if item["status"] == "CONDITIONALLY_SAFE"),
            "insufficient_data": sum(1 for item in accepted if item["status"] == "INSUFFICIENT_DATA"),
            "rejected": len(rejected),
        },
        "candidates": accepted[:limit],
        "rejected_candidates": rejected[:include_rejected_limit],
        "important_note": (
            "Candidates are generated, hard-filtered, and ranked deterministically. "
            "Scores are transparent planning scores, not ML predictions."
        ),
    }
