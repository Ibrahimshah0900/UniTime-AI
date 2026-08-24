from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.database import Base
from backend.enrollment_schemas import EnrollmentCreate
from backend.enrollment_service import create_student_enrollment, delete_student_enrollment, list_student_enrollments
from backend.models import User


def create_test_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_student(db, email: str) -> User:
    user = User(email=email, full_name="Test Student", password_hash=hash_password("Password123"), role="student", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def enrollment_request() -> EnrollmentCreate:
    return EnrollmentCreate(course_code="AI-301", section="A", semester="Fall 2026")


def test_create_and_list_student_enrollment():
    Session = create_test_session()
    with Session() as db:
        student = create_student(db, "student1@example.edu")
        created = create_student_enrollment(db, user_id=student.id, request=enrollment_request())
        enrollments = list_student_enrollments(db, student.id)
        assert len(enrollments) == 1
        assert enrollments[0].id == created.id
        assert enrollments[0].course_code == "AI-301"
        assert enrollments[0].section == "A"
        assert enrollments[0].semester == "Fall 2026"


def test_duplicate_enrollment_is_rejected():
    Session = create_test_session()
    with Session() as db:
        student = create_student(db, "student2@example.edu")
        create_student_enrollment(db, user_id=student.id, request=enrollment_request())
        with pytest.raises(HTTPException) as exc_info:
            create_student_enrollment(db, user_id=student.id, request=enrollment_request())
        assert exc_info.value.status_code == 409


def test_duplicate_enrollment_identity_is_case_insensitive():
    Session = create_test_session()
    with Session() as db:
        student = create_student(db, "student-case@example.edu")
        create_student_enrollment(
            db,
            user_id=student.id,
            request=EnrollmentCreate(
                course_code="ai-301",
                section="a",
                semester="FALL 2026",
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            create_student_enrollment(
                db,
                user_id=student.id,
                request=EnrollmentCreate(
                    course_code="AI-301",
                    section="A",
                    semester="fall 2026",
                ),
            )

        assert exc_info.value.status_code == 409


def test_student_can_delete_own_enrollment():
    Session = create_test_session()
    with Session() as db:
        student = create_student(db, "student3@example.edu")
        enrollment = create_student_enrollment(db, user_id=student.id, request=enrollment_request())
        delete_student_enrollment(db, user_id=student.id, enrollment_id=enrollment.id)
        assert list_student_enrollments(db, student.id) == []


def test_student_cannot_delete_another_students_enrollment():
    Session = create_test_session()
    with Session() as db:
        owner = create_student(db, "owner@example.edu")
        other = create_student(db, "other@example.edu")
        enrollment = create_student_enrollment(db, user_id=owner.id, request=enrollment_request())
        with pytest.raises(HTTPException) as exc_info:
            delete_student_enrollment(db, user_id=other.id, enrollment_id=enrollment.id)
        assert exc_info.value.status_code == 404
        assert len(list_student_enrollments(db, owner.id)) == 1
