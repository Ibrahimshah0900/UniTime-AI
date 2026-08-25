from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth_dependencies import require_coordinator_or_admin, require_verified_student
from backend.clash_report_schemas import (
    ClashReportCreate,
    ClashReportDetailResponse,
    ClashReportListResponse,
    ClashReportResolutionCandidatesResponse,
    ClashReportReviewUpdate,
    ClashReportStatus,
)
from backend.clash_report_service import (
    create_clash_report,
    get_clash_report,
    generate_clash_report_resolution_candidates,
    list_clash_reports,
    update_clash_report,
)
from backend.database import get_db
from backend.models import User
from backend.term_service import get_active_term


student_router = APIRouter(
    prefix="/student/clash-reports",
    tags=["Student Clash Reports"],
)
review_router = APIRouter(prefix="/clash-reports", tags=["Clash Report Review"])


@student_router.post("", response_model=ClashReportDetailResponse, status_code=201)
def submit_my_clash_report(
    request: ClashReportCreate,
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
):
    return create_clash_report(
        db,
        student_user_id=current_user.id,
        request=request,
    )


@student_router.get("", response_model=ClashReportListResponse)
def list_my_clash_reports(
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    term_id: int | None = Query(default=None, gt=0),
):
    return list_clash_reports(
        db,
        student_user_id=current_user.id,
        offset=offset,
        limit=limit,
        term_id=term_id,
    )


@student_router.get("/{report_id}", response_model=ClashReportDetailResponse)
def get_my_clash_report(
    report_id: int,
    current_user: Annotated[User, Depends(require_verified_student)],
    db: Session = Depends(get_db),
):
    return get_clash_report(
        db,
        report_id,
        student_user_id=current_user.id,
    )


@review_router.get("", response_model=ClashReportListResponse)
def get_clash_report_review_queue(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    status: ClashReportStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    term_id: int | None = Query(default=None, gt=0),
):
    selected_term_id = term_id or get_active_term(db).id
    return list_clash_reports(
        db,
        status=status,
        offset=offset,
        limit=limit,
        term_id=selected_term_id,
    )


@review_router.get("/{report_id}", response_model=ClashReportDetailResponse)
def get_clash_report_for_review(
    report_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return get_clash_report(db, report_id)


@review_router.get(
    "/{report_id}/resolution-candidates",
    response_model=ClashReportResolutionCandidatesResponse,
)
def get_clash_report_resolution_candidates(
    report_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    target_entry_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_rejected_limit: int = Query(default=20, ge=0, le=100),
):
    return generate_clash_report_resolution_candidates(
        db,
        report_id=report_id,
        target_entry_id=target_entry_id,
        limit=limit,
        include_rejected_limit=include_rejected_limit,
    )


@review_router.patch("/{report_id}", response_model=ClashReportDetailResponse)
def review_clash_report(
    report_id: int,
    request: ClashReportReviewUpdate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return update_clash_report(
        db,
        report_id=report_id,
        actor_user_id=current_user.id,
        request=request,
    )
