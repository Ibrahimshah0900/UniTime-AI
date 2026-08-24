from __future__ import annotations

from fastapi import (
    FastAPI,
    HTTPException,
)
from fastapi.testclient import TestClient

from backend.api_errors import (
    register_api_error_handlers,
)
from backend.api_middleware import (
    register_api_middleware,
)


def create_test_app() -> FastAPI:
    app = FastAPI()

    register_api_middleware(
        app
    )

    register_api_error_handlers(
        app
    )

    @app.get(
        "/conflict"
    )
    def conflict_endpoint():
        raise HTTPException(
            status_code=409,
            detail=(
                "Schedule conflict detected."
            ),
        )

    @app.get(
        "/items/{item_id}"
    )
    def item_endpoint(
        item_id: int,
    ):
        return {
            "item_id": item_id,
        }

    return app


def create_client() -> TestClient:
    return TestClient(
        create_test_app(),
        raise_server_exceptions=False,
    )


def test_http_exception_has_standard_shape():
    response = create_client().get(
        "/conflict"
    )

    assert response.status_code == 409

    body = response.json()

    assert body[
        "success"
    ] is False

    assert body[
        "error"
    ] == "Schedule conflict detected."

    assert body[
        "status_code"
    ] == 409

    assert body[
        "request_id"
    ]


def test_error_body_request_id_matches_header():
    response = create_client().get(
        "/conflict"
    )

    assert (
        response.json()[
            "request_id"
        ]
        == response.headers[
            "x-request-id"
        ]
    )


def test_not_found_uses_standard_shape():
    response = create_client().get(
        "/does-not-exist"
    )

    assert response.status_code == 404

    body = response.json()

    assert body[
        "success"
    ] is False

    assert body[
        "status_code"
    ] == 404

    assert body[
        "request_id"
    ]


def test_validation_error_is_standardized():
    response = create_client().get(
        "/items/not-an-integer"
    )

    assert response.status_code == 422

    body = response.json()

    assert body[
        "success"
    ] is False

    assert body[
        "error"
    ] == (
        "Request validation failed."
    )

    assert body[
        "status_code"
    ] == 422

    assert body[
        "request_id"
    ]

    assert len(
        body["details"]
    ) >= 1


def test_validation_error_does_not_echo_input():
    response = create_client().get(
        "/items/VERY_SECRET_BAD_VALUE"
    )

    body = response.json()

    serialized = str(
        body
    )

    assert (
        "VERY_SECRET_BAD_VALUE"
        not in serialized
    )

    for error in body[
        "details"
    ]:
        assert "input" not in error