from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.auth_security import create_access_token, hash_password
from backend.database import Base, get_db
from backend.models import TimetableEntry, User


READ_ONLY_COORDINATOR_PATHS = (
    "/timetable",
    "/clashes",
    "/clashes/room-suggestions",
    "/clashes/student-risk",
    "/clashes/student-groups",
    "/clashes/student-resolutions",
    "/optimizer/global",
    "/optimizer/plan",
    "/student-schedule-changes",
    "/changes",
    "/audit-trail",
    "/optimizer/executions",
)


def test_typed_operation_responses_validate_real_payloads():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as db:
        coordinator = User(
            email="contract-coordinator@example.edu",
            full_name="Contract Coordinator",
            password_hash=hash_password("Password123"),
            role="coordinator",
            is_active=True,
        )
        db.add(coordinator)
        db.add_all(
            [
                TimetableEntry(
                    course_code="CS-101",
                    semester="Fall 2026",
                    section="A",
                    faculty="Dr Ada",
                    room="C-101",
                    day="Monday",
                    start_time="09:00",
                    end_time="10:00",
                ),
                TimetableEntry(
                    course_code="MTH-101",
                    semester="Fall 2026",
                    section="A",
                    faculty="Dr Euler",
                    room="C-102",
                    day="Monday",
                    start_time="09:30",
                    end_time="10:30",
                ),
            ]
        )
        db.commit()
        db.refresh(coordinator)
        token = create_access_token(
            coordinator.id,
            token_version=coordinator.token_version,
        )

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = {"Authorization": f"Bearer {token}"}
            for path in READ_ONLY_COORDINATOR_PATHS:
                response = client.get(path, headers=headers)
                assert response.status_code == 200, (path, response.text)

            imported = client.post(
                "/timetable/import",
                headers=headers,
                files={
                    "file": (
                        "contract.csv",
                        (
                            "course_code,course_name,semester,section,faculty,"
                            "room,day,start_time,end_time,class_type\n"
                            "PHY-201,Mechanics,Fall 2026,A,Dr Curie,LAB-1,"
                            "Wednesday,11:00,12:00,lab\n"
                        ).encode("utf-8"),
                        "text/csv",
                    )
                },
            )
            assert imported.status_code == 200, imported.text
            assert imported.json()["imported"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
