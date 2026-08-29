from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.auth_security import hash_password
from backend.enrollment_conflict_graph import (
    build_enrollment_conflict_analysis,
    summarize_enrollment_conflicts,
)
from backend.models import (
    AcademicTerm,
    FacultyClassAssignment,
    LearningEvent,
    Notification,
    StudentClashReport,
    StudentEnrollment,
    StudentProfile,
    TimetableChange,
    TimetableEntry,
    User,
)
from backend.safe_candidate_service import generate_safe_candidates


DEMO_MARKER = "DEMO"
SYNTHETIC_EMAIL_DOMAIN = "synthetic.invalid"
BOOTSTRAP_TERM_CODE = "LEGACY-IMPORTED"


@dataclass(frozen=True, slots=True)
class DemoDataConfig:
    seed: int = 20260826
    student_count: int = 320
    faculty_count: int = 16
    room_count: int = 16
    sections: tuple[str, ...] = ("A", "B")
    semesters: int = 8
    courses_per_semester: int = 4

    def validate(self) -> None:
        if self.seed < 0:
            raise ValueError("Synthetic seed must be zero or greater.")
        if self.student_count < 8 or self.student_count > 10_000:
            raise ValueError("Synthetic student_count must be between 8 and 10000.")
        if self.faculty_count < self.semesters or self.faculty_count > 500:
            raise ValueError(
                "Synthetic faculty_count must be at least the semester count and at most 500."
            )
        if self.room_count < 4 or self.room_count > 500:
            raise ValueError("Synthetic room_count must be between 4 and 500.")
        if not self.sections or len(self.sections) > 12:
            raise ValueError("Synthetic sections must contain between 1 and 12 values.")
        if any(not section.strip() for section in self.sections):
            raise ValueError("Synthetic section values cannot be blank.")
        if self.semesters != 8:
            raise ValueError("The UniTime-AI demo dataset models exactly eight semesters.")
        if self.courses_per_semester < 3 or self.courses_per_semester > 8:
            raise ValueError("Synthetic courses_per_semester must be between 3 and 8.")


@dataclass(frozen=True, slots=True)
class DemoGenerationSummary:
    seed: int
    term_id: int
    term_code: str
    students: int
    faculty: int
    rooms: int
    courses: int
    sections: int
    enrollments: int
    timetable_entries: int
    intentional_conflict_pairs: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DemoBenchmarkResult:
    term_id: int
    timetable_entries: int
    enrollment_records: int
    verified_students: int
    confirmed_conflict_edges: int
    inferred_conflict_edges: int
    affected_students_across_confirmed_edges: int
    candidate_target_entry_id: int | None
    candidates_evaluated: int
    actionable_candidates: int
    runtime_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def assert_demo_database_is_pristine(db: Session) -> AcademicTerm:
    """Allow only a freshly migrated database with its migration bootstrap term."""

    populated_models = (
        User,
        StudentProfile,
        StudentEnrollment,
        FacultyClassAssignment,
        TimetableEntry,
        TimetableChange,
        StudentClashReport,
        Notification,
        LearningEvent,
    )
    populated = {
        model.__tablename__: _count(db, model)
        for model in populated_models
        if _count(db, model)
    }
    if populated:
        details = ", ".join(f"{name}={count}" for name, count in sorted(populated.items()))
        raise ValueError(
            "Synthetic generation refuses a non-empty application database "
            f"({details}). Use a new isolated demo database."
        )

    terms = list(db.scalars(select(AcademicTerm).order_by(AcademicTerm.id)).all())
    if len(terms) != 1 or terms[0].code != BOOTSTRAP_TERM_CODE:
        raise ValueError(
            "Synthetic generation requires a freshly migrated database containing only "
            "the migration bootstrap term."
        )
    return terms[0]


def _course_code(semester: int, course_index: int) -> str:
    return f"DEMO-S{semester}-C{course_index + 1:02d}"


def _student_registration(index: int) -> str:
    return f"DEMO-FA26-BAI-{index:04d}"


def generate_demo_data(
    db: Session,
    *,
    config: DemoDataConfig = DemoDataConfig(),
) -> DemoGenerationSummary:
    """Populate a freshly migrated, isolated database with deterministic synthetic data."""

    config.validate()
    bootstrap_term = assert_demo_database_is_pristine(db)
    rng = random.Random(config.seed)

    # Reuse the migration bootstrap term ID so every legacy default remains valid,
    # but make its synthetic identity unmistakable.
    bootstrap_term.code = "DEMO-FALL-2026"
    bootstrap_term.name = "DEMO — Fall 2026 (Synthetic)"
    bootstrap_term.status = "active"
    bootstrap_term.starts_on = date(2026, 8, 24)
    bootstrap_term.ends_on = date(2026, 12, 31)
    bootstrap_term.activated_at = bootstrap_term.activated_at
    bootstrap_term.archived_at = None
    term = bootstrap_term

    synthetic_password_hash = hash_password("SyntheticDemoOnly!2026")

    faculty_users: list[User] = []
    for index in range(1, config.faculty_count + 1):
        faculty = User(
            email=f"demo.faculty{index:03d}@{SYNTHETIC_EMAIL_DOMAIN}",
            full_name=f"DEMO Faculty {index:03d}",
            password_hash=synthetic_password_hash,
            role="faculty",
            is_active=True,
            must_change_password=False,
        )
        db.add(faculty)
        faculty_users.append(faculty)

    coordinator = User(
        email=f"demo.coordinator@{SYNTHETIC_EMAIL_DOMAIN}",
        full_name="DEMO Coordinator",
        password_hash=synthetic_password_hash,
        role="coordinator",
        is_active=True,
        must_change_password=False,
    )
    db.add(coordinator)
    db.flush()
    term.created_by_user_id = coordinator.id

    rooms = [f"DEMO-R{index:03d}" for index in range(1, config.room_count + 1)]
    course_codes = [
        _course_code(semester, course_index)
        for semester in range(1, config.semesters + 1)
        for course_index in range(config.courses_per_semester)
    ]

    # Faculty/course/timetable setup. The first two courses of every semester
    # intentionally overlap per section; the remaining courses are staggered.
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    slots = (
        ("08:30", "10:00"),
        ("10:00", "11:30"),
        ("11:30", "13:00"),
        ("14:00", "15:30"),
        ("15:30", "17:00"),
    )
    timetable_entries: list[TimetableEntry] = []
    assignment_rows: list[FacultyClassAssignment] = []
    intentional_pairs = 0
    faculty_by_semester = {
        semester: faculty_users[(semester - 1) % len(faculty_users)]
        for semester in range(1, config.semesters + 1)
    }

    for semester in range(1, config.semesters + 1):
        faculty = faculty_by_semester[semester]
        for section_index, section in enumerate(config.sections):
            conflict_day = days[(semester + section_index - 1) % len(days)]
            conflict_slot = slots[1]
            first_two_ids: list[TimetableEntry] = []
            for course_index in range(config.courses_per_semester):
                code = _course_code(semester, course_index)
                if course_index < 2:
                    day = conflict_day
                    start_time, end_time = conflict_slot
                else:
                    day = days[(semester + course_index + section_index) % len(days)]
                    start_time, end_time = slots[(course_index + semester) % len(slots)]
                    if day == conflict_day and (start_time, end_time) == conflict_slot:
                        start_time, end_time = slots[(course_index + semester + 1) % len(slots)]
                room = rooms[
                    (semester * 3 + section_index * config.courses_per_semester + course_index)
                    % len(rooms)
                ]
                entry = TimetableEntry(
                    term_id=term.id,
                    entry_kind="course",
                    course_code=code,
                    course_name=f"DEMO Synthetic Course S{semester}-{course_index + 1}",
                    semester=f"Semester {semester}",
                    section=section,
                    faculty=faculty.full_name,
                    room=room,
                    day=day,
                    start_time=start_time,
                    end_time=end_time,
                    class_type="lecture",
                    raw_text="DEMO SYNTHETIC DATA",
                    source="generated",
                )
                db.add(entry)
                timetable_entries.append(entry)
                if course_index < 2:
                    first_two_ids.append(entry)

                assignment_rows.append(
                    FacultyClassAssignment(
                        term_id=term.id,
                        faculty_user_id=faculty.id,
                        course_code=code,
                        section=section,
                        semester=f"Semester {semester}",
                        created_by_user_id=coordinator.id,
                    )
                )
            if len(first_two_ids) == 2:
                intentional_pairs += 1

    db.add_all(assignment_rows)
    db.flush()

    enrollments: list[StudentEnrollment] = []
    for index in range(1, config.student_count + 1):
        semester = ((index - 1) % config.semesters) + 1
        section = config.sections[((index - 1) // config.semesters) % len(config.sections)]
        user = User(
            email=f"demo.student{index:05d}@{SYNTHETIC_EMAIL_DOMAIN}",
            full_name=f"DEMO Student {index:05d}",
            password_hash=synthetic_password_hash,
            role="student",
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        db.add(
            StudentProfile(
                user_id=user.id,
                registration_number=_student_registration(index),
                department="DEMO Computing",
                program="DEMO BS Artificial Intelligence",
                batch="DEMO-2026",
                current_semester=semester,
                section=section,
                academic_status="active",
                is_verified=True,
                onboarding_completed=True,
                created_by_user_id=coordinator.id,
            )
        )

        # Every student takes the first two required courses, creating an
        # intentional enrollment-backed conflict. The remaining load is sampled
        # deterministically from the same semester.
        selected_indices = [0, 1]
        remaining = list(range(2, config.courses_per_semester))
        rng.shuffle(remaining)
        selected_indices.extend(remaining[: min(2, len(remaining))])
        for course_index in selected_indices:
            enrollment = StudentEnrollment(
                term_id=term.id,
                user_id=user.id,
                course_code=_course_code(semester, course_index),
                section=section,
                semester=f"Semester {semester}",
            )
            db.add(enrollment)
            enrollments.append(enrollment)

    db.commit()

    return DemoGenerationSummary(
        seed=config.seed,
        term_id=term.id,
        term_code=term.code,
        students=config.student_count,
        faculty=config.faculty_count,
        rooms=len(rooms),
        courses=len(course_codes),
        sections=len(config.sections),
        enrollments=len(enrollments),
        timetable_entries=len(timetable_entries),
        intentional_conflict_pairs=intentional_pairs,
    )


def benchmark_demo_resolver(db: Session, *, term_id: int) -> DemoBenchmarkResult:
    """Measure the deterministic conflict graph and candidate engine on demo data."""

    started = time.perf_counter()
    entries = list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.term_id == term_id)
            .order_by(TimetableEntry.id)
        ).all()
    )
    analysis = build_enrollment_conflict_analysis(db, entries, term_id=term_id)
    summary = summarize_enrollment_conflicts(analysis)
    confirmed = [risk for risk in analysis["risks"] if risk["risk_level"] == "confirmed"]
    affected = sum(int(risk.get("affected_student_count", 0)) for risk in confirmed)

    target_id: int | None = None
    generated = 0
    actionable = 0
    if confirmed:
        first = confirmed[0]
        pair = [first["entry_1"]["id"], first["entry_2"]["id"]]
        target_id = pair[0]
        candidates = generate_safe_candidates(
            db,
            entries=entries,
            target_entry_ids=[target_id],
            report_entry_ids=pair,
            limit=20,
            include_rejected_limit=0,
        )
        generated = int(candidates["summary"]["generated"])
        actionable = sum(
            1
            for candidate in candidates["candidates"]
            if candidate["status"] in {"SAFE", "CONDITIONALLY_SAFE"}
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return DemoBenchmarkResult(
        term_id=term_id,
        timetable_entries=len(entries),
        enrollment_records=int(summary["enrollment_records"]),
        verified_students=int(summary["verified_students"]),
        confirmed_conflict_edges=int(summary["confirmed"]),
        inferred_conflict_edges=int(summary["inferred"]),
        affected_students_across_confirmed_edges=affected,
        candidate_target_entry_id=target_id,
        candidates_evaluated=generated,
        actionable_candidates=actionable,
        runtime_ms=elapsed_ms,
    )


def is_safe_demo_database_path(path: Path, *, project_root: Path) -> bool:
    resolved = path.expanduser().resolve()
    development_db = (project_root / "data" / "unitime_ai.db").resolve()
    name = resolved.name.lower()
    return (
        resolved.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
        and ("demo" in name or "synthetic" in name)
        and resolved != development_db
    )
