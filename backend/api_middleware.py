from __future__ import annotations

import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.logging_config import get_logger


logger = get_logger(__name__)


def register_api_middleware(
    app: FastAPI,
) -> None:
    """
    Register application-wide request logging and
    unexpected-error handling.

    Existing FastAPI HTTPException responses remain handled
    by FastAPI normally.
    """

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next,
    ):
        request_id = uuid4().hex
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

            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": (
                        "Internal server error."
                    ),
                    "request_id": request_id,
                },
                headers={
                    "X-Request-ID": request_id,
                },
            )

        duration_ms = (
            time.perf_counter()
            - started_at
        ) * 1000

        response.headers[
            "X-Request-ID"
        ] = request_id

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