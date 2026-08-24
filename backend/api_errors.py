from __future__ import annotations

from typing import Any

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def get_request_id(
    request: Request,
) -> str | None:
    return getattr(
        request.state,
        "request_id",
        None,
    )


def safe_validation_errors(
    exc: RequestValidationError,
) -> list[dict[str, Any]]:
    """
    Return frontend-useful validation information without
    echoing submitted input values back to the client.
    """

    safe_errors = []

    for error in exc.errors():
        safe_errors.append(
            {
                "location": list(
                    error.get(
                        "loc",
                        (),
                    )
                ),
                "message": error.get(
                    "msg",
                    "Invalid value.",
                ),
                "type": error.get(
                    "type",
                    "validation_error",
                ),
            }
        )

    return safe_errors


def register_api_error_handlers(
    app: FastAPI,
) -> None:
    """
    Standardize expected API failures.

    Unexpected server errors remain handled by the global
    request middleware.
    """

    @app.exception_handler(
        StarletteHTTPException
    )
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ):
        request_id = get_request_id(
            request
        )

        if isinstance(
            exc.detail,
            str,
        ):
            message = exc.detail
            extra_detail = None
        else:
            message = "Request failed."
            extra_detail = exc.detail

        body: dict[str, Any] = {
            "success": False,
            "error": message,
            "status_code": (
                exc.status_code
            ),
            "request_id": request_id,
        }

        if extra_detail is not None:
            body["detail"] = (
                extra_detail
            )

        return JSONResponse(
            status_code=(
                exc.status_code
            ),
            content=body,
            headers=exc.headers,
        )

    @app.exception_handler(
        RequestValidationError
    )
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        request_id = get_request_id(
            request
        )

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": (
                    "Request validation failed."
                ),
                "status_code": 422,
                "request_id": (
                    request_id
                ),
                "details": (
                    safe_validation_errors(
                        exc
                    )
                ),
            },
        )