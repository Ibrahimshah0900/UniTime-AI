from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin
from backend.database import get_db
from backend.models import User
from backend.resolver_analytics_schemas import ResolverAnalyticsResponse
from backend.resolver_analytics_service import build_resolver_analytics


router = APIRouter(prefix="/resolver-analytics", tags=["Resolver Analytics"])


@router.get("", response_model=ResolverAnalyticsResponse)
def get_resolver_analytics(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    return build_resolver_analytics(db, term_id=term_id)
