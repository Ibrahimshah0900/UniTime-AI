from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin, require_faculty
from backend.database import get_db
from backend.faculty_schemas import (
    FacultyAssignmentCreate,
    FacultyAssignmentResponse,
    FacultyDirectoryResponse,
    FacultyFreeSlotsResponse,
    FacultyProvisionCreate,
    FacultyProvisionResponse,
)
from backend.faculty_service import (
    create_faculty_assignment,
    delete_faculty_assignment,
    get_faculty_timetable,
    get_faculty_free_slots,
    list_faculty_directory,
    list_faculty_assignments,
    provision_faculty_account,
)
from backend.models import User
from backend.schemas import TimetableEntryResponse


faculty_router = APIRouter(prefix="/faculty", tags=["Faculty"])
management_router = APIRouter(
    prefix="/faculty-assignments",
    tags=["Faculty Assignments"],
)
directory_router = APIRouter(
    prefix="/faculty-directory",
    tags=["Faculty Directory"],
)


@directory_router.get("", response_model=FacultyDirectoryResponse)
def get_faculty_directory(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_faculty_directory(
        db,
        search=search,
        offset=offset,
        limit=limit,
    )


@directory_router.post("", response_model=FacultyProvisionResponse, status_code=201)
def create_faculty_account(
    request: FacultyProvisionCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return provision_faculty_account(db, request)


@faculty_router.get("/assignments", response_model=list[FacultyAssignmentResponse])
def get_my_faculty_assignments(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    return list_faculty_assignments(
        db,
        faculty_user_id=current_user.id,
        term_id=term_id,
    )


@faculty_router.get("/timetable", response_model=list[TimetableEntryResponse])
def get_my_faculty_timetable(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    return get_faculty_timetable(db, current_user.id, term_id=term_id)



@faculty_router.get("/free-slots", response_model=FacultyFreeSlotsResponse)
def get_my_faculty_free_slots(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
    minimum_minutes: int = Query(default=30, ge=30, le=720),
):
    return get_faculty_free_slots(
        db,
        current_user.id,
        term_id=term_id,
        minimum_minutes=minimum_minutes,
    )


@management_router.get("", response_model=list[FacultyAssignmentResponse])
def get_managed_faculty_assignments(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    faculty_user_id: int | None = None,
    term_id: int | None = Query(default=None, gt=0),
):
    return list_faculty_assignments(
        db,
        faculty_user_id=faculty_user_id,
        term_id=term_id,
    )


@management_router.post("", response_model=FacultyAssignmentResponse, status_code=201)
def add_faculty_assignment(
    request: FacultyAssignmentCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return create_faculty_assignment(
        db,
        created_by_user_id=current_user.id,
        request=request,
    )


@management_router.delete("/{assignment_id}", status_code=204)
def remove_faculty_assignment(
    assignment_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
) -> Response:
    delete_faculty_assignment(db, assignment_id)
    return Response(status_code=204)
