from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api_middleware import register_api_middleware


def create_test_app() -> FastAPI:
    """
    Create an isolated FastAPI app so middleware tests do
    not touch the real UniTime-AI database or timetable.
    """

    app = FastAPI()

    register_api_middleware(app)

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
    app = create_test_app()

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.get(
        "/ok"
    )

    assert response.status_code == 200

    request_id = response.headers.get(
        "x-request-id"
    )

    assert request_id is not None
    assert len(request_id) > 0


def test_request_ids_are_unique():
    app = create_test_app()

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    first = client.get(
        "/ok"
    )

    second = client.get(
        "/ok"
    )

    first_id = first.headers.get(
        "x-request-id"
    )

    second_id = second.headers.get(
        "x-request-id"
    )

    assert first_id
    assert second_id
    assert first_id != second_id


def test_unhandled_error_returns_safe_json():
    app = create_test_app()

    client = TestClient(
        app,
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
        response.headers[
            "x-request-id"
        ]
        == body["request_id"]
    )


def test_internal_exception_is_not_leaked():
    app = create_test_app()

    client = TestClient(
        app,
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

    assert (
        "runtimeerror"
        not in body_text
    )


def test_not_found_response_still_has_request_id():
    app = create_test_app()

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.get(
        "/does-not-exist"
    )

    assert response.status_code == 404

    assert response.headers.get(
        "x-request-id"
    )