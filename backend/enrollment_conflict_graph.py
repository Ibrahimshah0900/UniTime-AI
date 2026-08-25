from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import StudentEnrollment, StudentProfile, TimetableEntry, User
from backend.schedule_matching import section_matches, semester_matches
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
    build_entry_summary,
    shared_sections,
    times_overlap,
)
from backend.term_service import get_active_term


@dataclass(frozen=True)
class EnrollmentConflictEvidence:
    term_id: int
    total_enrollment_records: int
    eligible_enrollment_records: int
    mapped_enrollment_records: int
    unmapped_enrollment_ids: tuple[int, ...]
    verified_student_ids: frozenset[int]
    entry_students: Mapping[int, frozenset[int]]


def _entry_pair(first_id: int, second_id: int) -> tuple[int, int]:
    return tuple(sorted((first_id, second_id)))


def _matching_entries(
    enrollment: StudentEnrollment,
    entries_by_course: dict[str, list[TimetableEntry]],
) -> list[TimetableEntry]:
    course_code = enrollment.course_code.strip().upper()
    return [
        entry
        for entry in entries_by_course.get(course_code, [])
        if section_matches(enrollment.section, entry.section)
        and semester_matches(enrollment.semester, entry.semester)
    ]


def _confirmed_risk(
    first: TimetableEntry,
    second: TimetableEntry,
    *,
    affected_student_count: int,
) -> dict:
    return {
        "type": "student_conflict_risk",
        "risk_type": "enrollment_backed_overlap",
        "risk_level": "confirmed",
        "score": 100,
        "day": first.day,
        "overlap": {
            "entry_1_time": f"{first.start_time}-{first.end_time}",
            "entry_2_time": f"{second.start_time}-{second.end_time}",
        },
        "shared_sections": sorted(shared_sections(first, second)),
        "same_course_level": False,
        "evidence_source": "enrollment",
        "affected_student_count": affected_student_count,
        "enrollment_coverage": "complete_for_edge",
        "evidence": [
            f"{affected_student_count} active verified student(s) are enrolled in both offerings.",
            "The two current timetable entries overlap in the active academic term.",
        ],
        "limitations": [],
        "entry_1": build_entry_summary(first),
        "entry_2": build_entry_summary(second),
    }


def _inferred_risk(
    risk: dict,
    *,
    first_has_coverage: bool,
    second_has_coverage: bool,
) -> dict:
    inferred = dict(risk)
    original_level = inferred["risk_level"]
    if original_level == "confirmed":
        inferred["risk_level"] = "probable"
        inferred["score"] = min(inferred.get("score", 0), 75)
    inferred["risk_type"] = f"inferred_{inferred['risk_type']}"
    inferred["evidence_source"] = "timetable_inference"
    inferred["affected_student_count"] = 0
    inferred["enrollment_coverage"] = (
        "partial" if first_has_coverage or second_has_coverage else "none"
    )
    limitations = list(inferred.get("limitations", []))
    limitations.append(
        "Enrollment coverage is incomplete for this pair, so no affected student is confirmed."
    )
    inferred["limitations"] = limitations
    return inferred


def build_enrollment_conflict_evidence(
    db: Session,
    entries: list[TimetableEntry],
    *,
    term_id: int | None = None,
) -> EnrollmentConflictEvidence:
    selected_term_id = term_id or get_active_term(db).id
    course_entries = [
        entry
        for entry in entries
        if getattr(entry, "entry_kind", "course") == "course"
    ]
    entries_by_course: dict[str, list[TimetableEntry]] = defaultdict(list)
    for entry in course_entries:
        if entry.course_code:
            entries_by_course[entry.course_code.strip().upper()].append(entry)

    total_enrollment_records = db.scalar(
        select(func.count(StudentEnrollment.id)).where(
            StudentEnrollment.term_id == selected_term_id
        )
    ) or 0
    eligible_enrollments = list(
        db.scalars(
            select(StudentEnrollment)
            .join(User, User.id == StudentEnrollment.user_id)
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .where(
                StudentEnrollment.term_id == selected_term_id,
                User.role == "student",
                User.is_active.is_(True),
                StudentProfile.is_verified.is_(True),
                StudentProfile.academic_status == "active",
            )
            .order_by(StudentEnrollment.user_id, StudentEnrollment.id)
        ).all()
    )

    entry_students: dict[int, set[int]] = defaultdict(set)
    mapped_enrollments = 0
    unmapped_enrollment_ids: list[int] = []
    verified_student_ids: set[int] = set()
    for enrollment in eligible_enrollments:
        verified_student_ids.add(enrollment.user_id)
        matches = _matching_entries(enrollment, entries_by_course)
        if not matches:
            unmapped_enrollment_ids.append(enrollment.id)
            continue
        mapped_enrollments += 1
        for entry in matches:
            entry_students[entry.id].add(enrollment.user_id)

    return EnrollmentConflictEvidence(
        term_id=selected_term_id,
        total_enrollment_records=total_enrollment_records,
        eligible_enrollment_records=len(eligible_enrollments),
        mapped_enrollment_records=mapped_enrollments,
        unmapped_enrollment_ids=tuple(unmapped_enrollment_ids),
        verified_student_ids=frozenset(verified_student_ids),
        entry_students=MappingProxyType(
            {
                entry_id: frozenset(student_ids)
                for entry_id, student_ids in entry_students.items()
            }
        ),
    )


def build_enrollment_conflict_analysis(
    db: Session,
    entries: list[TimetableEntry],
    *,
    term_id: int | None = None,
    evidence: EnrollmentConflictEvidence | None = None,
) -> dict:
    selected_evidence = evidence or build_enrollment_conflict_evidence(
        db,
        entries,
        term_id=term_id,
    )
    selected_term_id = term_id or selected_evidence.term_id
    if selected_term_id != selected_evidence.term_id:
        raise ValueError("Enrollment evidence belongs to a different academic term.")
    course_entries = [
        entry
        for entry in entries
        if getattr(entry, "entry_kind", "course") == "course"
    ]
    entry_students = selected_evidence.entry_students

    confirmed: list[dict] = []
    confirmed_pairs: set[tuple[int, int]] = set()
    for first, second in combinations(course_entries, 2):
        if not times_overlap(first, second):
            continue
        shared_students = entry_students.get(first.id, frozenset()) & entry_students.get(
            second.id,
            frozenset(),
        )
        if not shared_students:
            continue
        confirmed_pairs.add(_entry_pair(first.id, second.id))
        confirmed.append(
            _confirmed_risk(
                first,
                second,
                affected_student_count=len(shared_students),
            )
        )

    inferred: list[dict] = []
    for risk in analyze_student_conflicts(course_entries):
        first_id = risk["entry_1"]["id"]
        second_id = risk["entry_2"]["id"]
        pair = _entry_pair(first_id, second_id)
        if pair in confirmed_pairs:
            continue
        first_has_coverage = bool(entry_students.get(first_id))
        second_has_coverage = bool(entry_students.get(second_id))
        # When both offerings have enrollment coverage and share no students,
        # the heuristic signal is disproven rather than merely uncertain.
        if first_has_coverage and second_has_coverage:
            continue
        inferred.append(
            _inferred_risk(
                risk,
                first_has_coverage=first_has_coverage,
                second_has_coverage=second_has_coverage,
            )
        )

    risks = confirmed + inferred
    priority = {"confirmed": 0, "probable": 1, "possible": 2}
    risks.sort(
        key=lambda item: (
            priority[item["risk_level"]],
            -item["score"],
            item["day"],
            item["entry_1"]["start_time"],
            item["entry_1"]["id"],
            item["entry_2"]["id"],
        )
    )
    return {
        "risks": risks,
        "coverage": {
            "term_id": selected_term_id,
            "enrollment_records": selected_evidence.total_enrollment_records,
            "eligible_enrollment_records": selected_evidence.eligible_enrollment_records,
            "mapped_enrollment_records": selected_evidence.mapped_enrollment_records,
            "unmapped_enrollment_records": len(selected_evidence.unmapped_enrollment_ids),
            "verified_students": len(selected_evidence.verified_student_ids),
            "entries_with_enrollment_data": len(entry_students),
            "entry_enrollment_counts": {
                entry_id: len(student_ids)
                for entry_id, student_ids in entry_students.items()
            },
            "enrollment_backed_edges": len(confirmed),
            "inferred_edges": len(inferred),
            "unmapped_enrollment_ids": list(selected_evidence.unmapped_enrollment_ids),
        },
    }


def summarize_enrollment_conflicts(analysis: dict) -> dict:
    risks = analysis["risks"]
    coverage = analysis["coverage"]
    confirmed = sum(1 for risk in risks if risk["risk_level"] == "confirmed")
    probable = sum(1 for risk in risks if risk["risk_level"] == "probable")
    possible = sum(1 for risk in risks if risk["risk_level"] == "possible")
    return {
        "total": len(risks),
        "confirmed": confirmed,
        "probable": probable,
        "possible": possible,
        "enrollment_backed": coverage["enrollment_backed_edges"],
        "inferred": coverage["inferred_edges"],
        "enrollment_records": coverage["enrollment_records"],
        "verified_students": coverage["verified_students"],
        "unmapped_enrollment_records": coverage["unmapped_enrollment_records"],
        "important_note": (
            "Confirmed conflicts are backed by active verified student enrollments. "
            "Probable and possible conflicts are explicitly inferred only where enrollment coverage is incomplete."
        ),
    }
