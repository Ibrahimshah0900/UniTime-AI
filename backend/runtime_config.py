from __future__ import annotations

from typing import Any

from backend.config import (
    ALLOWED_HOSTS,
    APP_ENV,
    CORS_ORIGINS,
    IS_PRODUCTION,
)
from backend.config import AUTH_SECRET_KEY, DEFAULT_AUTH_SECRET_KEY
from backend.database import DATABASE_URL


def validate_runtime_config() -> dict[str, Any]:
    """
    Validate deployment-critical application settings.

    Development remains permissive.

    Production rejects configuration that is clearly unsafe
    or incomplete.
    """

    errors: list[str] = []

    if not CORS_ORIGINS:
        errors.append(
            "CORS_ORIGINS cannot be empty."
        )

    if not ALLOWED_HOSTS:
        errors.append(
            "ALLOWED_HOSTS cannot be empty."
        )

    if "*" in CORS_ORIGINS:
        errors.append(
            "Wildcard CORS origins are not allowed."
        )

    if IS_PRODUCTION:
        if (
            AUTH_SECRET_KEY == DEFAULT_AUTH_SECRET_KEY
            or len(AUTH_SECRET_KEY) < 32
        ):
            errors.append(
                "Production AUTH_SECRET_KEY must be a custom secret "
                "with at least 32 characters."
            )
        if APP_ENV != "production":
            errors.append(
                "Production environment is inconsistent."
            )

        if "*" in ALLOWED_HOSTS:
            errors.append(
                "Wildcard ALLOWED_HOSTS is not allowed "
                "in production."
            )

        localhost_hosts = {
            "localhost",
            "127.0.0.1",
            "testserver",
        }

        if set(ALLOWED_HOSTS).issubset(
            localhost_hosts
        ):
            errors.append(
                "Production ALLOWED_HOSTS must contain "
                "a deployed API host."
            )

        localhost_origins = (
            "localhost",
            "127.0.0.1",
        )

        if all(
            any(
                local in origin
                for local in localhost_origins
            )
            for origin in CORS_ORIGINS
        ):
            errors.append(
                "Production CORS_ORIGINS must contain "
                "a deployed frontend origin."
            )

    if errors:
        raise RuntimeError(
            "Invalid runtime configuration: "
            + " ".join(errors)
        )

    return {
        "environment": APP_ENV,
        "production": IS_PRODUCTION,
        "database_backend": (
            DATABASE_URL.split(
                ":",
                1,
            )[0]
        ),
        "cors_origins": len(
            CORS_ORIGINS
        ),
        "allowed_hosts": len(
            ALLOWED_HOSTS
        ),
    }


def api_documentation_settings() -> dict[str, str | None]:
    """
    Keep interactive API documentation available during
    development but hide it on production deployments.
    """

    if IS_PRODUCTION:
        return {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
        }

    return {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }