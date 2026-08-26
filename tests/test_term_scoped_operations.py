from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.auth_service import create_privileged_account
from backend.auth_types import UserRole
from backend.database import Base, get_db


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"identifier": "admin.termops@example.edu", "password": "Password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_read_only_operations_are_scoped_to_selected_academic_term():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        with Session() as db:
            create_privileged_account(
                db,
                email="admin.termops@example.edu",
                full_name="Term Operations Admin",
                password="Password123",
                role=UserRole.ADMIN,
            )

        headers = _login(client)
        terms = client.get("/academic-terms", headers=headers)
        assert terms.status_code == 200
        active_id = terms.json()["active_term_id"]
        assert active_id is not None

        planning = client.post(
            "/academic-terms",
            headers=headers,
            json={
                "code": "TERMOPS-SPRING-2027",
                "name": "Term Ops Spring 2027",
                "starts_on": "2027-01-11",
                "ends_on": "2027-05-28",
            },
        )
        assert planning.status_code == 201
        planning_id = planning.json()["id"]

        active_entry = client.post(
            "/timetable",
            headers=headers,
            json={
                "course_code": "ACTIVE-101",
                "course_name": "Active Only",
                "semester": "Fall 2026",
                "section": "A",
                "faculty": "Dr Active",
                "room": "ACTIVE-R1",
                "day": "Monday",
                "start_time": "08:00",
                "end_time": "09:00",
            },
        )
        assert active_entry.status_code == 201
        assert active_entry.json()["term_id"] == active_id

        planning_ids: list[int] = []
        for code, faculty in (("PLAN-201", "Dr Plan A"), ("PLAN-202", "Dr Plan B")):
            created = client.post(
                f"/timetable?term_id={planning_id}",
                headers=headers,
                json={
                    "course_code": code,
                    "course_name": code,
                    "semester": "Spring 2027",
                    "section": "A",
                    "faculty": faculty,
                    "room": "PLAN-R1",
                    "day": "Tuesday",
                    "start_time": "10:00",
                    "end_time": "11:00",
                },
            )
            assert created.status_code == 201
            planning_ids.append(created.json()["id"])

        active_clashes = client.get("/clashes", headers=headers)
        assert active_clashes.status_code == 200
        assert active_clashes.json()["total"] == 0

        planning_clashes = client.get(
            f"/clashes?term_id={planning_id}",
            headers=headers,
        )
        assert planning_clashes.status_code == 200
        assert planning_clashes.json()["total"] >= 1
        seen_ids = {
            clash["entry_1"]["id"]
            for clash in planning_clashes.json()["clashes"]
        } | {
            clash["entry_2"]["id"]
            for clash in planning_clashes.json()["clashes"]
        }
        assert set(planning_ids).issubset(seen_ids)
        assert active_entry.json()["id"] not in seen_ids

        room = client.get(
            f"/clashes/room-suggestions?term_id={planning_id}",
            headers=headers,
        )
        assert room.status_code == 200
        assert room.json()["room_clashes"] >= 1

        risk = client.get(
            f"/clashes/student-risk?term_id={planning_id}",
            headers=headers,
        )
        assert risk.status_code == 200
        assert risk.json()["summary"]["enrollment_records"] == 0

        assert client.get(
            f"/clashes/student-groups?term_id={planning_id}",
            headers=headers,
        ).status_code == 200
        assert client.get(
            f"/clashes/student-resolutions?term_id={planning_id}",
            headers=headers,
        ).status_code == 200
        assert client.get(
            f"/optimizer/global?term_id={planning_id}",
            headers=headers,
        ).status_code == 200
        assert client.get(
            f"/optimizer/plan?term_id={planning_id}",
            headers=headers,
        ).status_code == 200

        missing = client.get("/clashes?term_id=999999", headers=headers)
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
