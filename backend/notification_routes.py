from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth_dependencies import get_current_user, require_coordinator_or_admin
from backend.database import get_db
from backend.models import User
from backend.notification_schemas import (
    NotificationJobResponse,
    NotificationListResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    NotificationType,
)
from backend.notification_service import (
    get_notification_preferences,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    process_due_notifications,
    update_notification_preferences,
)
from backend.operation_schemas import NotificationReadAllResponse


router = APIRouter(tags=["Notifications"])
job_router = APIRouter(prefix="/notification-jobs", tags=["Notification Jobs"])


@router.get(
    "/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
def get_my_notification_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return get_notification_preferences(db, current_user.id)


@router.put(
    "/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
def update_my_notification_preferences(
    request: NotificationPreferenceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return update_notification_preferences(db, user_id=current_user.id, request=request)


@router.get("/notifications", response_model=NotificationListResponse)
def get_my_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    unread_only: bool = False,
    type: NotificationType | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_notifications(
        db,
        user_id=current_user.id,
        unread_only=unread_only,
        notification_type=type,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def read_my_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return mark_notification_read(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    )


@router.post(
    "/notifications/read-all",
    response_model=NotificationReadAllResponse,
)
def read_all_my_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return {"updated": mark_all_notifications_read(db, user_id=current_user.id)}


@job_router.post("/process", response_model=NotificationJobResponse)
def process_notification_jobs(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return process_due_notifications(db)
