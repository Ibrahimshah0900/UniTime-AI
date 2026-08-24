from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_student
from backend.database import get_db
from backend.enrollment_service import get_student_timetable
from backend.models import User
from backend.schemas import TimetableEntryResponse


router = APIRouter(prefix="/student", tags=["Student"])


@router.get("/timetable", response_model=list[TimetableEntryResponse])
def get_my_timetable(
    current_user: Annotated[User, Depends(require_student)],
    db: Session = Depends(get_db),
):
    return get_student_timetable(db, current_user.id)
