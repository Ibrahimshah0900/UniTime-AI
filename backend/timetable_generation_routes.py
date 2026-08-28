from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin
from backend.concurrency import acquire_timetable_write_lock
from backend.database import get_db
from backend.models import User
from backend.timetable_generation_schemas import (
    TimetableGenerationApplyRequest,
    TimetableGenerationApplyResponse,
    TimetableGenerationPreviewRequest,
    TimetableGenerationPreviewResponse,
)
from backend.timetable_generation_service import (
    apply_timetable_generation,
    preview_timetable_generation,
)


router = APIRouter(
    prefix="/timetable-generation",
    tags=["Timetable Generation"],
)


@router.post(
    "/preview",
    response_model=TimetableGenerationPreviewResponse,
)
def preview_generation(
    request: TimetableGenerationPreviewRequest,
    current_user: Annotated[
        User,
        Depends(require_coordinator_or_admin),
    ],
    db: Session = Depends(get_db),
):
    return preview_timetable_generation(
        db,
        term_id=request.term_id,
    )


@router.post(
    "/apply",
    response_model=TimetableGenerationApplyResponse,
)
def apply_generation(
    request: TimetableGenerationApplyRequest,
    current_user: Annotated[
        User,
        Depends(require_coordinator_or_admin),
    ],
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    return apply_timetable_generation(
        db,
        term_id=request.term_id,
        preview_id=request.preview_id,
    )
