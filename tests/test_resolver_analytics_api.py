from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.models import (
    AcademicTerm,
    StudentClashReport,
    StudentClashReportEvent,
    StudentClashReportItem,
    StudentEnrollment,
    StudentProfile,
    TimetableEntry,
    User,
)
from backend.resolver_analytics_routes import router
from backend.student_resolution_applier import ResolutionLearningEvent, StudentScheduleChange


def create_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(AcademicTerm(id=1, code="TEST-TERM", name="Test Term", status="active"))
        db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session, engine


def create_user(Session, email: str, role: str) -> User:
    with Session() as db:
        user = User(
            email=email,
            full_name=email.split("@")[0].title(),
            password_hash=hash_password("Password123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        if role == "student":
            db.add(
                StudentProfile(
                    user_id=user.id,
                    registration_number=f"TEST-{user.id:04d}",
                    department="Computing",
                    program="BS AI",
                    batch="2026",
                    current_semester=3,
                    section="A",
                    is_verified=True,
                    onboarding_completed=True,
                )
            )
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_resolver_analytics_requires_coordinator_or_admin():
    app, client, Session, engine = create_context()
    try:
        assert client.get("/resolver-analytics").status_code == 401
        student = create_user(Session, "student@example.edu", "student")
        app.dependency_overrides[get_current_user] = lambda: student
        assert client.get("/resolver-analytics").status_code == 403
    finally:
        engine.dispose()


def test_resolver_analytics_empty_term_is_truthful_and_zero_safe():
    app, client, Session, engine = create_context()
    try:
        coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
        app.dependency_overrides[get_current_user] = lambda: coordinator
        response = client.get("/resolver-analytics")
        assert response.status_code == 200
        payload = response.json()
        assert payload["current_confirmed_conflicts"] == 0
        assert payload["report_total"] == 0
        assert payload["undo_rate"]["value"] is None
        assert payload["undo_rate"]["available"] is True
        assert payload["recommendation_acceptance_rate"]["available"] is False
    finally:
        engine.dispose()


def test_resolver_analytics_uses_live_conflicts_and_persisted_resolution_events():
    app, client, Session, engine = create_context()
    try:
        coordinator = create_user(Session, "coordinator@example.edu", "coordinator")
        first_student = create_user(Session, "one@example.edu", "student")
        second_student = create_user(Session, "two@example.edu", "student")
        with Session() as db:
            first = TimetableEntry(
                term_id=1,
                course_code="AI-301",
                section="A",
                semester="Semester 3",
                faculty="Faculty A",
                room="R1",
                day="Monday",
                start_time="10:00",
                end_time="11:00",
            )
            second = TimetableEntry(
                term_id=1,
                course_code="CS-210",
                section="A",
                semester="Semester 3",
                faculty="Faculty B",
                room="R2",
                day="Monday",
                start_time="10:30",
                end_time="11:30",
            )
            db.add_all([first, second])
            db.flush()
            for student in (first_student, second_student):
                db.add_all(
                    [
                        StudentEnrollment(term_id=1, user_id=student.id, course_code="AI-301", section="A", semester="Semester 3"),
                        StudentEnrollment(term_id=1, user_id=student.id, course_code="CS-210", section="A", semester="Semester 3"),
                    ]
                )
            created = datetime(2026, 8, 1, 8, 0, 0)
            report1 = StudentClashReport(
                term_id=1,
                student_user_id=first_student.id,
                student_registration_number_snapshot="TEST-ONE",
                student_name_snapshot="Student One",
                student_email_snapshot="one@example.edu",
                student_department_snapshot="Computing",
                student_program_snapshot="BS AI",
                student_batch_snapshot="2026",
                student_semester_snapshot=3,
                student_section_snapshot="A",
                conflict_fingerprint="a" * 64,
                status="resolved",
                resolution_reason="timetable_changed",
                resolution_note="Resolved",
                created_at=created,
                updated_at=created + timedelta(hours=4),
            )
            report2 = StudentClashReport(
                term_id=1,
                student_user_id=second_student.id,
                student_registration_number_snapshot="TEST-TWO",
                student_name_snapshot="Student Two",
                student_email_snapshot="two@example.edu",
                student_department_snapshot="Computing",
                student_program_snapshot="BS AI",
                student_batch_snapshot="2026",
                student_semester_snapshot=3,
                student_section_snapshot="A",
                conflict_fingerprint="a" * 64,
                status="resolved",
                resolution_reason="timetable_changed",
                resolution_note="Shared resolution",
                created_at=created,
                updated_at=created + timedelta(hours=4),
            )
            db.add_all([report1, report2])
            db.flush()
            for report in (report1, report2):
                db.add_all(
                    [
                        StudentClashReportItem(report_id=report.id, timetable_entry_id=first.id, course_code="AI-301", section="A", semester="Semester 3", day="Monday", start_time="10:00", end_time="11:00"),
                        StudentClashReportItem(report_id=report.id, timetable_entry_id=second.id, course_code="CS-210", section="A", semester="Semester 3", day="Monday", start_time="10:30", end_time="11:30"),
                    ]
                )
            db.add(
                StudentClashReportEvent(
                    report_id=report1.id,
                    actor_user_id=coordinator.id,
                    action="resolution_applied",
                    from_status="under_review",
                    to_status="resolved",
                    note="Resolved",
                    created_at=created + timedelta(hours=4),
                )
            )
            db.add(
                StudentClashReportEvent(
                    report_id=report2.id,
                    actor_user_id=coordinator.id,
                    action="resolved_by_shared_timetable_change",
                    from_status="submitted",
                    to_status="resolved",
                    note="Shared resolution",
                    created_at=created + timedelta(hours=4),
                )
            )
            change = StudentScheduleChange(
                term_id=1,
                entry_id=first.id,
                group_id=None,
                report_id=report1.id,
                actor_user_id=coordinator.id,
                candidate_id="c" * 24,
                safety_status="CONDITIONALLY_SAFE",
                report_resolution_note="Resolved",
                change_type="clash_report_resolution",
                old_day="Monday",
                old_start_time="10:00",
                old_end_time="11:00",
                new_day="Tuesday",
                new_start_time="10:00",
                new_end_time="11:00",
                score=80.0,
                reasons_json="[]",
                risk_cost_before=200,
                risk_cost_after=0,
                total_risks_before=1,
                total_risks_after=0,
                undone=False,
            )
            db.add(change)
            db.flush()
            features = {
                "feature_schema_version": "1.0",
                "hard_constraints_passed": True,
                "safety_status": "CONDITIONALLY_SAFE",
                "duration_minutes": 60,
                "affected_students": 2,
                "confirmed_conflicts_removed": 1,
                "inferred_conflicts_removed": 0,
                "structural_clashes_removed": 0,
                "conflict_groups_removed": 1,
                "weighted_risk_reduction": 200,
                "day_distance": 1,
                "time_shift_minutes": 0,
                "late_slot": False,
                "missing_metadata_count": 1,
            }
            base_event = dict(
                term_id=1,
                report_id=report1.id,
                change_id=change.id,
                actor_user_id=coordinator.id,
                candidate_id="c" * 24,
                ranker_id="deterministic_weighted",
                ranker_version="1.0",
                feature_schema_version="1.0",
                safety_status="CONDITIONALLY_SAFE",
                features_json=json.dumps(features),
                rank_score=80,
            )
            db.add(ResolutionLearningEvent(event_type="candidate_applied", outcome_label="accepted", **base_event))
            db.add(ResolutionLearningEvent(event_type="resolution_undone", outcome_label="undone", **base_event))
            db.add(ResolutionLearningEvent(event_type="resolution_redone", outcome_label="redone", **base_event))
            db.commit()

        app.dependency_overrides[get_current_user] = lambda: coordinator
        response = client.get("/resolver-analytics")
        assert response.status_code == 200
        payload = response.json()
        assert payload["current_confirmed_conflicts"] == 1
        assert payload["current_affected_student_instances"] == 2
        assert payload["report_total"] == 2
        assert payload["report_cluster_count"] == 1
        assert payload["grouped_duplicate_reports"] == 1
        assert payload["average_first_resolution_hours"] == 4.0
        assert payload["resolution_applications"] == 1
        assert payload["resolution_undos"] == 1
        assert payload["resolution_redos"] == 1
        assert payload["confirmed_conflicts_removed_by_applications"] == 1
        assert payload["shared_resolved_reports"] == 1
        assert payload["shared_resolution_percentage"] == 50.0
        assert payload["undo_rate"]["value"] == 100.0
        assert payload["redo_rate"]["value"] == 100.0
    finally:
        engine.dispose()
