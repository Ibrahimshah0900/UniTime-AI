from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_verified_student
from backend.database import get_db
from backend.enrollment_schemas import (
    EnrollmentConflictValidationResponse,
    EnrollmentCreate,
    EnrollmentCreateResponse,
    EnrollmentResponse,
)
from backend.enrollment_service import (
    create_student_enrollment,
    delete_student_enrollment,
    list_student_enrollments,
    validate_student_enrollment,
)
from backend.models import User


router = APIRouter(prefix="/student/enrollments", tags=["Student Enrollments"])


@router.get("", response_model=list[EnrollmentResponse])
def get_my_enrollments(
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
):
    return list_student_enrollments(db, current_user.id)


@router.post("", response_model=EnrollmentCreateResponse, status_code=201)
def add_my_enrollment(
    request: EnrollmentCreate,
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
):
    return create_student_enrollment(
        db,
        user_id=current_user.id,
        request=request,
    )


@router.post("/validate", response_model=EnrollmentConflictValidationResponse)
def validate_my_enrollment(
    request: EnrollmentCreate,
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
):
    return validate_student_enrollment(
        db,
        user_id=current_user.id,
        request=request,
    )


@router.delete("/{enrollment_id}", status_code=204)
def remove_my_enrollment(
    enrollment_id: int,
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
) -> Response:
    delete_student_enrollment(
        db,
        user_id=current_user.id,
        enrollment_id=enrollment_id,
    )
    return Response(status_code=204)
