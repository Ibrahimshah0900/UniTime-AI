from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.account_schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    PasswordChange,
    ProfileUpdate,
)
from backend.auth_security import hash_password, verify_password
from backend.models import User


def update_profile(db: Session, *, user: User, request: ProfileUpdate) -> User:
    managed_user = db.get(User, user.id)
    if managed_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    managed_user.full_name = request.full_name
    db.commit()
    db.refresh(managed_user)
    return managed_user


def change_password(db: Session, *, user: User, request: PasswordChange) -> None:
    managed_user = db.get(User, user.id)
    if managed_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if not verify_password(request.current_password, managed_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    managed_user.password_hash = hash_password(request.new_password)
    db.commit()


def create_admin_managed_user(db: Session, request: AdminUserCreate) -> User:
    if db.scalar(select(User.id).where(User.email == request.email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role=request.role.value,
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


def list_admin_users(
    db: Session,
    *,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    filters = []
    if role is not None:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    users = list(
        db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.full_name, User.id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {"users": users, "total": total, "offset": offset, "limit": limit}


def update_admin_managed_user(
    db: Session,
    *,
    actor: User,
    target_user_id: int,
    request: AdminUserUpdate,
) -> User:
    target = db.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == actor.id and (
        request.is_active is False
        or (request.role is not None and request.role.value != "admin")
    ):
        raise HTTPException(
            status_code=409,
            detail="Administrators cannot deactivate or remove their own admin role.",
        )
    if target.role == "admin" and (
        request.is_active is False
        or (request.role is not None and request.role.value != "admin")
    ):
        other_active_admins = db.scalar(
            select(func.count(User.id)).where(
                User.role == "admin",
                User.is_active.is_(True),
                User.id != target.id,
            )
        ) or 0
        if other_active_admins == 0:
            raise HTTPException(
                status_code=409,
                detail="The last active administrator cannot be deactivated or demoted.",
            )
    if request.full_name is not None:
        target.full_name = request.full_name
    if request.role is not None:
        target.role = request.role.value
    if request.is_active is not None:
        target.is_active = request.is_active
    db.commit()
    db.refresh(target)
    return target
