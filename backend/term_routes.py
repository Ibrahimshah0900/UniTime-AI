from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth_dependencies import get_current_user, require_coordinator_or_admin
from backend.database import get_db
from backend.models import User
from backend.term_schemas import (
    AcademicTermCreate,
    AcademicTermListResponse,
    AcademicTermResponse,
)
from backend.term_service import (
    activate_academic_term,
    archive_academic_term,
    create_academic_term,
    get_active_term,
    list_academic_terms,
)


router = APIRouter(prefix="/academic-terms", tags=["Academic Terms"])


@router.get("", response_model=AcademicTermListResponse)
def get_academic_terms(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return list_academic_terms(db)


@router.get("/current", response_model=AcademicTermResponse)
def get_current_academic_term(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return get_active_term(db)


@router.post("", response_model=AcademicTermResponse, status_code=201)
def create_term(
    request: AcademicTermCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return create_academic_term(
        db,
        actor_user_id=current_user.id,
        request=request,
    )


@router.post("/{term_id}/activate", response_model=AcademicTermResponse)
def activate_term(
    term_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return activate_academic_term(db, term_id=term_id)


@router.post("/{term_id}/archive", response_model=AcademicTermResponse)
def archive_term(
    term_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return archive_academic_term(
        db,
        term_id=term_id,
        actor_role=current_user.role,
    )
