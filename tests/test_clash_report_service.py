from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.clash_report_schemas import ClashReportCreate, ClashReportReviewUpdate
from backend.clash_report_service import (
    create_clash_report,
    get_clash_report,
    list_clash_reports,
    update_clash_report,
)
from backend.database import Base
from backend.models import StudentEnrollment, TimetableEntry, User


def create_test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_user(db, email: str, role: str = "student") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].replace(".", " ").title(),
        password_hash=hash_password("Password123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_schedule(db, student: User) -> tuple[TimetableEntry, TimetableEntry, TimetableEntry]:
    db.add_all(
        [
            StudentEnrollment(
                user_id=student.id,
                course_code="AI-301",
                section="A",
                semester="Fall 2026",
            ),
            StudentEnrollment(
                user_id=student.id,
                course_code="CS-210",
                section="B",
                semester="Fall 2026",
            ),
            StudentEnrollment(
                user_id=student.id,
                course_code="MTH-110",
                section="A",
                semester="Fall 2026",
            ),
        ]
    )
    first = TimetableEntry(
        course_code="AI-301",
        course_name="Artificial Intelligence",
        section="A,C",
        semester="Fall 2026",
        day="Monday",
        start_time="10:00",
        end_time="11:00",
    )
    second = TimetableEntry(
        course_code="CS-210",
        course_name="Algorithms",
        section="B",
        semester="Fall 2026",
        day="Monday",
        start_time="10:30",
        end_time="11:30",
    )
    non_overlapping = TimetableEntry(
        course_code="MTH-110",
        course_name="Calculus",
        section="A",
        semester="Fall 2026",
        day="Tuesday",
        start_time="09:00",
        end_time="10:00",
    )
    db.add_all([first, second, non_overlapping])
    db.commit()
    for entry in (first, second, non_overlapping):
        db.refresh(entry)
    return first, second, non_overlapping


def report_request(*entry_ids: int) -> ClashReportCreate:
    return ClashReportCreate(
        timetable_entry_ids=list(entry_ids),
        notes="These classes overlap every Monday.",
        evidence_reference="student-portal/schedule/123",
    )


def test_submission_captures_snapshots_and_initial_event():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu")
        first, second, _ = seed_schedule(db, student)

        result = create_clash_report(
            db,
            student_user_id=student.id,
            request=report_request(first.id, second.id),
        )

        assert result["status"] == "submitted"
        assert [item.course_code for item in result["items"]] == ["AI-301", "CS-210"]
        assert result["events"][0].action == "submitted"
        assert result["events"][0].actor_user_id == student.id

        first.course_code = "AI-999"
        first.start_time = "12:00"
        db.commit()
        persisted = get_clash_report(db, result["id"], student_user_id=student.id)
        assert persisted["items"][0].course_code == "AI-301"
        assert persisted["items"][0].start_time == "10:00"


def test_submission_rejects_unowned_or_missing_timetable_entries():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu")
        first, _, _ = seed_schedule(db, student)
        unrelated = TimetableEntry(
            course_code="PHY-100",
            day="Monday",
            start_time="10:15",
            end_time="11:15",
        )
        db.add(unrelated)
        db.commit()
        db.refresh(unrelated)

        with pytest.raises(HTTPException) as exc_info:
            create_clash_report(
                db,
                student_user_id=student.id,
                request=report_request(first.id, unrelated.id),
            )

        assert exc_info.value.status_code == 422


def test_submission_requires_an_actual_time_overlap():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu")
        first, _, non_overlapping = seed_schedule(db, student)

        with pytest.raises(HTTPException) as exc_info:
            create_clash_report(
                db,
                student_user_id=student.id,
                request=report_request(first.id, non_overlapping.id),
            )

        assert exc_info.value.status_code == 422
        assert "do not overlap" in exc_info.value.detail


def test_student_ownership_is_enforced_for_list_and_detail():
    Session = create_test_session()
    with Session() as db:
        owner = create_user(db, "owner@example.edu")
        other = create_user(db, "other@example.edu")
        first, second, _ = seed_schedule(db, owner)
        report = create_clash_report(
            db,
            student_user_id=owner.id,
            request=report_request(first.id, second.id),
        )

        assert list_clash_reports(db, student_user_id=owner.id)["total"] == 1
        assert list_clash_reports(db, student_user_id=other.id)["total"] == 0
        with pytest.raises(HTTPException) as exc_info:
            get_clash_report(db, report["id"], student_user_id=other.id)
        assert exc_info.value.status_code == 404


def test_review_lifecycle_is_enforced_and_fully_audited():
    Session = create_test_session()
    with Session() as db:
        student = create_user(db, "student@example.edu")
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        first, second, _ = seed_schedule(db, student)
        report = create_clash_report(
            db,
            student_user_id=student.id,
            request=report_request(first.id, second.id),
        )

        under_review = update_clash_report(
            db,
            report_id=report["id"],
            actor_user_id=coordinator.id,
            request=ClashReportReviewUpdate(status="under_review"),
        )
        resolved = update_clash_report(
            db,
            report_id=report["id"],
            actor_user_id=coordinator.id,
            request=ClashReportReviewUpdate(
                status="resolved",
                resolution_note="The CS class was moved to Tuesday.",
            ),
        )

        assert under_review["status"] == "under_review"
        assert resolved["status"] == "resolved"
        assert resolved["resolution_note"] == "The CS class was moved to Tuesday."
        assert [event.to_status for event in resolved["events"]] == [
            "submitted",
            "under_review",
            "resolved",
        ]
        assert resolved["events"][-1].actor_user_id == coordinator.id

        with pytest.raises(HTTPException) as exc_info:
            update_clash_report(
                db,
                report_id=report["id"],
                actor_user_id=coordinator.id,
                request=ClashReportReviewUpdate(status="under_review"),
            )
        assert exc_info.value.status_code == 409


def test_duplicate_reports_link_to_a_canonical_report():
    Session = create_test_session()
    with Session() as db:
        first_student = create_user(db, "first@example.edu")
        second_student = create_user(db, "second@example.edu")
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        first, second, _ = seed_schedule(db, first_student)
        for course_code, section in (("AI-301", "A"), ("CS-210", "B")):
            db.add(
                StudentEnrollment(
                    user_id=second_student.id,
                    course_code=course_code,
                    section=section,
                    semester="Fall 2026",
                )
            )
        db.commit()
        canonical = create_clash_report(
            db,
            student_user_id=first_student.id,
            request=report_request(first.id, second.id),
        )
        duplicate = create_clash_report(
            db,
            student_user_id=second_student.id,
            request=report_request(first.id, second.id),
        )

        updated = update_clash_report(
            db,
            report_id=duplicate["id"],
            actor_user_id=coordinator.id,
            request=ClashReportReviewUpdate(
                status="duplicate",
                duplicate_of_report_id=canonical["id"],
                resolution_note="Same classes and time window as the first report.",
            ),
        )

        assert updated["status"] == "duplicate"
        assert updated["duplicate_of_report_id"] == canonical["id"]

        queue = list_clash_reports(db, status="duplicate")
        assert queue["total"] == 1
        assert queue["reports"][0]["id"] == duplicate["id"]
