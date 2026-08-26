from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin
from backend.data_quality_schemas import DataQualityReportResponse
from backend.data_quality_service import run_data_quality_report
from backend.database import get_db
from backend.models import User


router = APIRouter(prefix="/data-quality", tags=["Data Quality"])


@router.get("", response_model=DataQualityReportResponse)
def get_data_quality_report(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    return run_data_quality_report(db, term_id=term_id)
