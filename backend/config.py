from __future__ import annotations

import os


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://127.0.0.1:3000,"
    "http://localhost:5173,"
    "http://127.0.0.1:5173"
)


def _parse_origins(value: str) -> list[str]:
    """
    Convert a comma-separated CORS_ORIGINS value into
    a clean list of explicit frontend origins.
    """

    return [
        origin.strip()
        for origin in value.split(",")
        if origin.strip()
    ]


APP_ENV = os.getenv(
    "APP_ENV",
    "development",
).strip().lower()


CORS_ORIGINS = _parse_origins(
    os.getenv(
        "CORS_ORIGINS",
        DEFAULT_CORS_ORIGINS,
    )
)


IS_PRODUCTION = APP_ENV == "production"