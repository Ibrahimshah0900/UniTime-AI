from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.account_schemas import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserUpdate,
    PasswordChange,
    ProfileUpdate,
)
from backend.account_service import (
    change_password,
    create_admin_managed_user,
    list_admin_users,
    update_admin_managed_user,
    update_profile,
)
from backend.auth_dependencies import get_current_user, require_admin
from backend.auth_schemas import UserResponse
from backend.auth_types import UserRole
from backend.database import get_db
from backend.models import User


account_router = APIRouter(prefix="/account", tags=["Account"])
admin_router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


@account_router.patch("/profile", response_model=UserResponse)
def update_my_profile(
    request: ProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return update_profile(db, user=current_user, request=request)


@account_router.post("/change-password", status_code=204)
def change_my_password(
    request: PasswordChange,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    change_password(db, user=current_user, request=request)


@admin_router.get("", response_model=AdminUserListResponse)
def get_users(
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
    role: UserRole | None = None,
    is_active: bool | None = None,
    search: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_admin_users(
        db,
        role=role.value if role is not None else None,
        is_active=is_active,
        search=search,
        offset=offset,
        limit=limit,
    )


@admin_router.post("", response_model=UserResponse, status_code=201)
def create_user(
    request: AdminUserCreate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return create_admin_managed_user(db, request)


@admin_router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    request: AdminUserUpdate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return update_admin_managed_user(
        db,
        actor=current_user,
        target_user_id=user_id,
        request=request,
    )
