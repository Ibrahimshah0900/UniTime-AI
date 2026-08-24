from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth_dependencies import get_current_user
from backend.dashboard_service import get_dashboard
from backend.database import get_db
from backend.models import User


class DashboardResponse(BaseModel):
    role: str
    generated_for_day: str
    data: dict[str, Any]


router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_my_dashboard(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return get_dashboard(db, current_user)
