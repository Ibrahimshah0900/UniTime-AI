from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from backend.auth_dependencies import get_current_user, require_coordinator_or_admin
from backend.database import get_db
from backend.models import User
from backend.student_identity_schemas import (
    RosterImportResponse,
    StudentIdentityListResponse,
    StudentIdentityResponse,
    StudentIdentityUpdate,
    StudentOnboardingUpdate,
    StudentProvisionCreate,
    StudentProvisionResponse,
    TemporaryCredentialResponse,
)
from backend.student_identity_service import (
    complete_student_onboarding,
    get_student_identity,
    list_student_identities,
    provision_student,
    reset_student_temporary_password,
    update_student_identity,
)
from backend.student_roster_importer import import_student_roster


management_router = APIRouter(prefix="/students", tags=["Student Provisioning"])
account_router = APIRouter(prefix="/account/student-profile", tags=["Account"])


@management_router.get("", response_model=StudentIdentityListResponse)
def get_students(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=200),
    is_verified: bool | None = None,
    is_active: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_student_identities(
        db,
        search=search,
        is_verified=is_verified,
        is_active=is_active,
        offset=offset,
        limit=limit,
    )


@management_router.post("", response_model=StudentProvisionResponse, status_code=201)
def create_student(
    request: StudentProvisionCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return provision_student(db, actor_user_id=current_user.id, request=request)


@management_router.post("/import", response_model=RosterImportResponse)
async def import_students(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    file: UploadFile = File(...),
    dry_run: bool = Query(default=True),
    update_existing: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return await import_student_roster(
        file,
        db,
        actor_user_id=current_user.id,
        dry_run=dry_run,
        update_existing=update_existing,
    )


@management_router.get("/{user_id}", response_model=StudentIdentityResponse)
def get_student(
    user_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return get_student_identity(db, user_id)


@management_router.patch("/{user_id}", response_model=StudentIdentityResponse)
def update_student(
    user_id: int,
    request: StudentIdentityUpdate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return update_student_identity(db, user_id=user_id, request=request)


@management_router.post(
    "/{user_id}/temporary-password",
    response_model=TemporaryCredentialResponse,
)
def reset_temporary_password(
    user_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return reset_student_temporary_password(db, user_id=user_id)


@account_router.get("", response_model=StudentIdentityResponse)
def get_my_student_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return get_student_identity(db, current_user.id)


@account_router.patch("", response_model=StudentIdentityResponse)
def complete_my_student_profile(
    request: StudentOnboardingUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return complete_student_onboarding(db, user=current_user, request=request)
