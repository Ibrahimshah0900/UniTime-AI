from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import (
    TrustedHostMiddleware,
)

from backend.api_middleware import (
    register_api_middleware,
)


def create_test_app(
    *,
    trusted_hosts: bool = False,
) -> FastAPI:
    app = FastAPI()

    if trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                "testserver",
                "allowed.example",
            ],
        )

    register_api_middleware(
        app
    )

    @app.get("/ok")
    def ok_endpoint():
        return {
            "status": "ok",
        }

    @app.get("/error")
    def error_endpoint():
        raise RuntimeError(
            "secret internal failure"
        )

    return app


def test_success_response_has_request_id():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ok"
    )

    assert response.status_code == 200
    assert response.headers.get(
        "x-request-id"
    )


def test_request_ids_are_unique():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    first = client.get("/ok")
    second = client.get("/ok")

    assert (
        first.headers["x-request-id"]
        != second.headers["x-request-id"]
    )


def test_unhandled_error_returns_safe_json():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/error"
    )

    assert response.status_code == 500

    body = response.json()

    assert body["success"] is False

    assert (
        body["error"]
        == "Internal server error."
    )

    assert body["request_id"]

    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_internal_exception_is_not_leaked():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/error"
    )

    body_text = response.text.lower()

    assert (
        "secret internal failure"
        not in body_text
    )

    assert "runtimeerror" not in body_text


def test_not_found_response_has_request_id():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/does-not-exist"
    )

    assert response.status_code == 404
    assert response.headers.get(
        "x-request-id"
    )


def test_security_headers_are_present():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ok"
    )

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        response.headers[
            "x-frame-options"
        ]
        == "DENY"
    )

    assert (
        response.headers[
            "referrer-policy"
        ]
        == "no-referrer"
    )

    assert (
        response.headers[
            "permissions-policy"
        ]
        == (
            "camera=(), microphone=(), "
            "geolocation=()"
        )
    )


def test_security_headers_exist_on_500():
    client = TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/error"
    )

    assert response.status_code == 500

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        response.headers[
            "x-frame-options"
        ]
        == "DENY"
    )


def test_trusted_host_accepts_allowed_host():
    client = TestClient(
        create_test_app(
            trusted_hosts=True
        ),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ok",
        headers={
            "Host": "allowed.example",
        },
    )

    assert response.status_code == 200


def test_trusted_host_rejects_unknown_host():
    client = TestClient(
        create_test_app(
            trusted_hosts=True
        ),
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ok",
        headers={
            "Host": "evil.example",
        },
    )

    assert response.status_code == 400