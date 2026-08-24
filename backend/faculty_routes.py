from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin, require_faculty
from backend.database import get_db
from backend.faculty_schemas import FacultyAssignmentCreate, FacultyAssignmentResponse
from backend.faculty_service import (
    create_faculty_assignment,
    delete_faculty_assignment,
    get_faculty_timetable,
    list_faculty_assignments,
)
from backend.models import User
from backend.schemas import TimetableEntryResponse


faculty_router = APIRouter(prefix="/faculty", tags=["Faculty"])
management_router = APIRouter(
    prefix="/faculty-assignments",
    tags=["Faculty Assignments"],
)


@faculty_router.get("/assignments", response_model=list[FacultyAssignmentResponse])
def get_my_faculty_assignments(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
):
    return list_faculty_assignments(db, faculty_user_id=current_user.id)


@faculty_router.get("/timetable", response_model=list[TimetableEntryResponse])
def get_my_faculty_timetable(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
):
    return get_faculty_timetable(db, current_user.id)


@management_router.get("", response_model=list[FacultyAssignmentResponse])
def get_managed_faculty_assignments(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    faculty_user_id: int | None = None,
):
    return list_faculty_assignments(db, faculty_user_id=faculty_user_id)


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
