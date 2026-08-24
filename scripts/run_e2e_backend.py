from __future__ import annotations

import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

E2E_DATABASE = (PROJECT_ROOT / "data" / "e2e.db").resolve()
DATA_DIRECTORY = (PROJECT_ROOT / "data").resolve()
if not E2E_DATABASE.is_relative_to(DATA_DIRECTORY):
    raise RuntimeError("E2E database must remain inside the project data directory.")

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{E2E_DATABASE.as_posix()}"
os.environ["AUTH_SECRET_KEY"] = "unitime-e2e-secret-key-with-32-characters"
os.environ["ALLOWED_HOSTS"] = "127.0.0.1,localhost,testserver"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:4173"


def prepare_database() -> None:
    if E2E_DATABASE.exists():
        E2E_DATABASE.unlink()

    from alembic import command
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    from backend.auth_security import hash_password
    from backend.database import SessionLocal
    from backend.models import (
        FacultyClassAssignment,
        StudentClashReport,
        StudentClashReportEvent,
        StudentClashReportItem,
        StudentEnrollment,
        TimetableEntry,
        User,
    )
    from backend.notification_service import add_notification

    password_hash = hash_password("Password123!")
    with SessionLocal() as db:
        student = User(email="student.e2e@example.edu", full_name="E2E Student", password_hash=password_hash, role="student", is_active=True)
        faculty = User(email="faculty.e2e@example.edu", full_name="E2E Faculty", password_hash=password_hash, role="faculty", is_active=True)
        coordinator = User(email="coordinator.e2e@example.edu", full_name="E2E Coordinator", password_hash=password_hash, role="coordinator", is_active=True)
        admin = User(email="admin.e2e@example.edu", full_name="E2E Admin", password_hash=password_hash, role="admin", is_active=True)
        db.add_all([student, faculty, coordinator, admin])
        db.flush()

        ai_entry = TimetableEntry(
            course_code="AI-301",
            course_name="Artificial Intelligence",
            semester="Fall 2026",
            section="A",
            faculty="E2E Faculty",
            room="LAB-1",
            day="Monday",
            start_time="09:00",
            end_time="10:00",
            class_type="lab",
        )
        math_entry = TimetableEntry(
            course_code="MTH-201",
            course_name="Discrete Mathematics",
            semester="Fall 2026",
            section="A",
            faculty="Dr Euler",
            room="LAB-1",
            day="Monday",
            start_time="09:30",
            end_time="10:30",
            class_type="lecture",
        )
        db.add_all(
            [
                StudentEnrollment(user_id=student.id, course_code="AI-301", section="A", semester="Fall 2026"),
                StudentEnrollment(user_id=student.id, course_code="MTH-201", section="A", semester="Fall 2026"),
                FacultyClassAssignment(
                    faculty_user_id=faculty.id,
                    course_code="AI-301",
                    section="A",
                    semester="Fall 2026",
                    created_by_user_id=coordinator.id,
                ),
                ai_entry,
                math_entry,
            ]
        )
        db.flush()
        report = StudentClashReport(
            student_user_id=student.id,
            status="submitted",
            notes="Seeded overlapping classes for coordinator review.",
        )
        db.add(report)
        db.flush()
        for entry in (ai_entry, math_entry):
            db.add(
                StudentClashReportItem(
                    report_id=report.id,
                    timetable_entry_id=entry.id,
                    course_code=entry.course_code or "Class",
                    section=entry.section,
                    semester=entry.semester,
                    day=entry.day,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                )
            )
        db.add(
            StudentClashReportEvent(
                report_id=report.id,
                actor_user_id=student.id,
                action="submitted",
                to_status="submitted",
                note="Seeded E2E clash report.",
            )
        )
        add_notification(
            db,
            user_id=student.id,
            notification_type="schedule_change",
            title="Welcome to the E2E timetable",
            message="Your seeded timetable is ready for verification.",
            dedup_key="e2e-welcome",
        )
        db.commit()


def main() -> None:
    prepare_database()
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
