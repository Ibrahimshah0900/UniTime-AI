from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth_schemas import RegisterRequest, normalize_email
from backend.auth_security import hash_password, verify_password
from backend.auth_types import UserRole
from backend.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


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


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
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
