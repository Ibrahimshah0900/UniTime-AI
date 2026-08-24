from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api_errors import register_api_error_handlers
from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.models import User
from backend.notification_routes import job_router, router
from backend.notification_service import add_notification


def create_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = FastAPI()
    register_api_error_handlers(app)
    app.include_router(router)
    app.include_router(job_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def create_user(Session, email: str, role: str) -> User:
    with Session() as db:
        user = User(
            email=email,
            full_name=email.split("@")[0].title(),
            password_hash=hash_password("Password123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_notification_routes_require_authentication():
    _, client, _ = create_context()
    assert client.get("/notifications").status_code == 401
    assert client.get("/notification-preferences").status_code == 401
    assert client.post("/notification-jobs/process").status_code == 401


def test_user_can_update_preferences_and_read_notifications():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    app.dependency_overrides[get_current_user] = lambda: student

    defaults = client.get("/notification-preferences")
    assert defaults.status_code == 200
    assert defaults.json()["class_reminder_minutes"] == 15

    updated = client.put(
        "/notification-preferences",
        json={
            "class_reminder_minutes": 30,
            "daily_summary_enabled": True,
            "daily_summary_time": "06:45",
            "schedule_change_enabled": True,
            "clash_report_updates_enabled": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["daily_summary_time"] == "06:45"

    with Session() as db:
        notification = add_notification(
            db,
            user_id=student.id,
            notification_type="schedule_change",
            title="Schedule changed",
            message="A class moved.",
        )
        db.commit()
        db.refresh(notification)
        notification_id = notification.id

    listed = client.get("/notifications?unread_only=true")
    assert listed.status_code == 200
    assert listed.json()["unread_count"] == 1

    marked = client.patch(f"/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None


def test_notification_ownership_is_enforced():
    app, client, Session = create_context()
    owner = create_user(Session, "owner@example.edu", "student")
    other = create_user(Session, "other@example.edu", "student")
    with Session() as db:
        notification = add_notification(
            db,
            user_id=owner.id,
            notification_type="schedule_change",
            title="Changed",
            message="Changed",
        )
        db.commit()
        db.refresh(notification)
        notification_id = notification.id

    app.dependency_overrides[get_current_user] = lambda: other
    assert client.patch(f"/notifications/{notification_id}/read").status_code == 404


def test_only_coordinator_or_admin_can_process_notification_jobs():
    app, client, Session = create_context()
    student = create_user(Session, "student@example.edu", "student")
    coordinator = create_user(Session, "coordinator@example.edu", "coordinator")

    app.dependency_overrides[get_current_user] = lambda: student
    assert client.post("/notification-jobs/process").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: coordinator
    response = client.post("/notification-jobs/process")
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Karachi"
