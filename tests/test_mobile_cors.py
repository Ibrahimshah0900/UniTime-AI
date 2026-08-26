from fastapi.testclient import TestClient

from backend.app import app


def test_capacitor_login_preflight_is_allowed():
    client = TestClient(app)
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "capacitor://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "capacitor://localhost"
