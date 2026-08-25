from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth_schemas import (
    RegisterRequest,
    normalize_email,
    normalize_registration_number,
)
from backend.auth_security import hash_password, verify_password
from backend.auth_types import UserRole
from backend.models import StudentProfile, User


_DUMMY_PASSWORD_HASH = hash_password("unitime-ai-login-timing-sentinel")


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def get_user_by_registration_number(db: Session, registration_number: str) -> User | None:
    return db.scalar(
        select(User)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(
            StudentProfile.registration_number
            == normalize_registration_number(registration_number)
        )
    )


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_student_account(db: Session, request: RegisterRequest) -> User:
    if get_user_by_email(db, request.email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    try:
        db.add(user)
        db.flush()
        db.add(
            StudentProfile(
                user_id=user.id,
                registration_number=f"DEV-{user.id:08d}",
                department="Self-registered",
                program="Self-registered",
                batch="Unverified",
                current_semester=1,
                section="Unassigned",
                academic_status="active",
                is_verified=False,
                onboarding_completed=True,
            )
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    except Exception:
        db.rollback()
        raise

    return user


def authenticate_user(
    db: Session,
    *,
    password: str,
    identifier: str | None = None,
    email: str | None = None,
) -> User | None:
    login_identifier = identifier or email
    if login_identifier is None or (identifier is not None and email is not None):
        raise ValueError("Provide exactly one login identifier.")
    user = (
        get_user_by_email(db, login_identifier)
        if "@" in login_identifier
        else get_user_by_registration_number(db, login_identifier)
    )
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    password_matches = verify_password(password, user.password_hash)
    if not user.is_active or not password_matches:
        return None
    return user

def create_privileged_account(db: Session, *, email: str, full_name: str, password: str, role: UserRole) -> User:
    if role not in {UserRole.FACULTY, UserRole.COORDINATOR, UserRole.ADMIN}:
        raise ValueError("Privileged accounts must use faculty, coordinator, or admin role.")

    normalized_email = normalize_email(email)
    normalized_name = " ".join(full_name.split())
    if len(normalized_name) < 2:
        raise ValueError("Full name is required.")
    if not 8 <= len(password) <= 128:
        raise ValueError("Password must contain between 8 and 128 characters.")
    if get_user_by_email(db, normalized_email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(email=normalized_email, full_name=normalized_name, password_hash=hash_password(password), role=role.value, is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    except Exception:
        db.rollback()
        raise
    return user
