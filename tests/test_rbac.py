from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import app
from backend.auth_dependencies import get_current_user, require_coordinator_or_admin


MUTATION_ROUTES = [
    ("POST", "/timetable"),
    ("DELETE", "/timetable/999999"),
    ("POST", "/timetable/import"),
    ("POST", "/optimizer/plan/apply"),
    ("POST", "/optimizer/global/apply-best"),
    ("POST", "/clashes/student-groups/999999/apply-best-fix"),
    ("POST", "/student-schedule-changes/999999/undo"),
    ("POST", "/student-schedule-changes/999999/redo"),
    ("PATCH", "/timetable/999999/room"),
    ("POST", "/clashes/room/999998/999999/apply-best-fix"),
    ("POST", "/changes/999999/undo"),
    ("POST", "/changes/999999/redo"),
    ("POST", "/optimizer/executions/999999/undo"),
    ("POST", "/optimizer/executions/999999/redo"),
]


@pytest.mark.parametrize("method,path", MUTATION_ROUTES)
def test_mutation_routes_require_coordinator_or_admin(method: str, path: str):
    client = TestClient(app)

    anonymous = client.request(method, path, json={})
    assert anonymous.status_code == 401

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role="student",
        is_active=True,
    )
    try:
        student = client.request(method, path, json={})
        assert student.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_coordinator_admin_role_policy():
    for role in ("student", "faculty"):
        with pytest.raises(HTTPException) as exc_info:
            require_coordinator_or_admin(SimpleNamespace(role=role))
        assert exc_info.value.status_code == 403

    for role in ("coordinator", "admin"):
        user = SimpleNamespace(role=role)
        assert require_coordinator_or_admin(user) is user
