from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import verify_password
from backend.auth_service import authenticate_user, create_privileged_account
from backend.auth_types import UserRole
from backend.database import Base


def create_test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.mark.parametrize(
    "role",
    [UserRole.FACULTY, UserRole.COORDINATOR, UserRole.ADMIN],
)
def test_create_privileged_account(role: UserRole):
    Session = create_test_session()
    with Session() as db:
        user = create_privileged_account(
            db,
            email="PRIVILEGED@EXAMPLE.EDU",
            full_name="  Privileged   User  ",
            password="Password123",
            role=role,
        )

        assert user.email == "privileged@example.edu"
        assert user.full_name == "Privileged User"
        assert user.role == role.value
        assert user.is_active is True
        assert user.password_hash != "Password123"
        assert verify_password("Password123", user.password_hash)


def test_privileged_account_can_authenticate():
    Session = create_test_session()
    with Session() as db:
        create_privileged_account(
            db,
            email="coordinator@example.edu",
            full_name="Coordinator User",
            password="Password123",
            role=UserRole.COORDINATOR,
        )

        user = authenticate_user(
            db,
            email="coordinator@example.edu",
            password="Password123",
        )
        assert user is not None
        assert user.role == "coordinator"


def test_student_role_cannot_use_privileged_provisioning():
    Session = create_test_session()
    with Session() as db:
        with pytest.raises(ValueError):
            create_privileged_account(
                db,
                email="student@example.edu",
                full_name="Student User",
                password="Password123",
                role=UserRole.STUDENT,
            )


def test_duplicate_privileged_email_is_rejected():
    Session = create_test_session()
    with Session() as db:
        create_privileged_account(
            db,
            email="admin@example.edu",
            full_name="Admin User",
            password="Password123",
            role=UserRole.ADMIN,
        )

        with pytest.raises(HTTPException) as exc_info:
            create_privileged_account(
                db,
                email="ADMIN@EXAMPLE.EDU",
                full_name="Another Admin",
                password="Password456",
                role=UserRole.ADMIN,
            )

        assert exc_info.value.status_code == 409
