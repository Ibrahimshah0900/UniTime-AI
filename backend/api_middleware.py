from __future__ import annotations

import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from backend.config import IS_PRODUCTION
from backend.logging_config import get_logger


logger = get_logger(__name__)


def apply_security_headers(
    response: Response,
) -> None:
    """
    Add baseline browser/API security headers.

    HSTS is enabled only in production because local
    development normally uses plain HTTP.
    """

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), microphone=(), geolocation=()"
    )

    if IS_PRODUCTION:
        response.headers[
            "Strict-Transport-Security"
        ] = (
            "max-age=31536000; "
            "includeSubDomains"
        )


def register_api_middleware(
    app: FastAPI,
) -> None:
    """
    Register application-wide:

    - request IDs
    - request logging
    - safe unexpected-error responses
    - baseline security headers

    Existing FastAPI HTTPException behavior remains intact.
    """

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next,
    ):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = await call_next(
                request
            )

        except Exception:
            duration_ms = (
                time.perf_counter()
                - started_at
            ) * 1000

            logger.exception(
                (
                    "Unhandled request error | "
                    "request_id=%s | "
                    "method=%s | "
                    "path=%s | "
                    "duration_ms=%.2f"
                ),
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )

            response = JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": (
                        "Internal server error."
                    ),
                    "request_id": request_id,
                },
            )

            response.headers[
                "X-Request-ID"
            ] = request_id

            apply_security_headers(
                response
            )

            return response

        duration_ms = (
            time.perf_counter()
            - started_at
        ) * 1000

        response.headers[
            "X-Request-ID"
        ] = request_id

        apply_security_headers(
            response
        )

        logger.info(
            (
                "Request completed | "
                "request_id=%s | "
                "method=%s | "
                "path=%s | "
                "status=%s | "
                "duration_ms=%.2f"
            ),
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response