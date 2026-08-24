from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.database import Base
from backend.faculty_schemas import FacultyAssignmentCreate
from backend.faculty_service import (
    create_faculty_assignment,
    delete_faculty_assignment,
    get_faculty_timetable,
    list_faculty_assignments,
)
from backend.models import TimetableEntry, User


def create_test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_user(db, email: str, role: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].title(),
        password_hash=hash_password("Password123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def assignment_request(user_id: int) -> FacultyAssignmentCreate:
    return FacultyAssignmentCreate(
        faculty_user_id=user_id,
        course_code="AI-301",
        section="A",
        semester="Fall 2026",
    )


def test_coordinator_can_create_list_and_delete_assignment():
    Session = create_test_session()
    with Session() as db:
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        faculty = create_user(db, "faculty@example.edu", "faculty")

        created = create_faculty_assignment(
            db,
            created_by_user_id=coordinator.id,
            request=assignment_request(faculty.id),
        )
        assignments = list_faculty_assignments(db, faculty_user_id=faculty.id)

        assert created["faculty_user_id"] == faculty.id
        assert created["faculty_email"] == "faculty@example.edu"
        assert created["created_by_user_id"] == coordinator.id
        assert [assignment["id"] for assignment in assignments] == [created["id"]]

        delete_faculty_assignment(db, created["id"])
        assert list_faculty_assignments(db, faculty_user_id=faculty.id) == []


def test_assignment_requires_an_active_faculty_account():
    Session = create_test_session()
    with Session() as db:
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        student = create_user(db, "student@example.edu", "student")

        with pytest.raises(HTTPException) as exc_info:
            create_faculty_assignment(
                db,
                created_by_user_id=coordinator.id,
                request=assignment_request(student.id),
            )

        assert exc_info.value.status_code == 422


def test_duplicate_faculty_assignment_is_rejected():
    Session = create_test_session()
    with Session() as db:
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        faculty = create_user(db, "faculty@example.edu", "faculty")
        request = assignment_request(faculty.id)
        create_faculty_assignment(
            db,
            created_by_user_id=coordinator.id,
            request=request,
        )

        with pytest.raises(HTTPException) as exc_info:
            create_faculty_assignment(
                db,
                created_by_user_id=coordinator.id,
                request=request,
            )

        assert exc_info.value.status_code == 409


def test_faculty_timetable_uses_stable_course_section_and_semester_matching():
    Session = create_test_session()
    with Session() as db:
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        faculty = create_user(db, "faculty@example.edu", "faculty")
        create_faculty_assignment(
            db,
            created_by_user_id=coordinator.id,
            request=assignment_request(faculty.id),
        )
        combined_section = TimetableEntry(
            course_code="AI-301",
            section="A,C",
            semester=None,
            faculty="DrAI",
            day="Monday",
            start_time="10:00",
            end_time="11:00",
        )
        wrong_section = TimetableEntry(
            course_code="AI-301",
            section="B",
            semester="Fall 2026",
            faculty="DrAI",
            day="Tuesday",
            start_time="10:00",
            end_time="11:00",
        )
        wrong_course = TimetableEntry(
            course_code="CS-210",
            section="A",
            semester="Fall 2026",
            faculty="DrAI",
            day="Wednesday",
            start_time="10:00",
            end_time="11:00",
        )
        db.add_all([combined_section, wrong_section, wrong_course])
        db.commit()

        timetable = get_faculty_timetable(db, faculty.id)

        assert [entry.id for entry in timetable] == [combined_section.id]


def test_faculty_assignment_lists_are_isolated_by_user():
    Session = create_test_session()
    with Session() as db:
        coordinator = create_user(db, "coordinator@example.edu", "coordinator")
        first = create_user(db, "first@example.edu", "faculty")
        second = create_user(db, "second@example.edu", "faculty")
        create_faculty_assignment(
            db,
            created_by_user_id=coordinator.id,
            request=assignment_request(first.id),
        )

        assert len(list_faculty_assignments(db, faculty_user_id=first.id)) == 1
        assert list_faculty_assignments(db, faculty_user_id=second.id) == []
        assert get_faculty_timetable(db, second.id) == []
