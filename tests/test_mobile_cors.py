from fastapi.testclient import TestClient

from backend.app import app


def _assert_login_preflight_is_allowed(
    *,
    origin: str,
    host: str = "testserver",
) -> None:
    client = TestClient(app)

    response = client.options(
        "/auth/login",
        headers={
            "Host": host,
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_capacitor_custom_scheme_login_preflight_is_allowed():
    _assert_login_preflight_is_allowed(
        origin="capacitor://localhost",
    )


def test_capacitor_android_emulator_login_preflight_is_allowed():
    _assert_login_preflight_is_allowed(
        origin="https://localhost",
        host="10.0.2.2:8000",
    )
