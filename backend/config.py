from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://127.0.0.1:3000,"
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "https://localhost,"
    "capacitor://localhost"
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

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).strip().upper()

DEFAULT_ALLOWED_HOSTS = (
    "localhost,127.0.0.1,10.0.2.2,testserver"
)

ALLOWED_HOSTS = _parse_origins(
    os.getenv(
        "ALLOWED_HOSTS",
        DEFAULT_ALLOWED_HOSTS,
    )
)

def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f'{name} must be an integer.') from exc
    if value < 1:
        raise RuntimeError(f'{name} must be at least 1.')
    return value


def _boolean_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f'{name} must be a boolean value.')

MAX_TIMETABLE_UPLOAD_MB = _positive_int_env('MAX_TIMETABLE_UPLOAD_MB', 10)
MAX_TIMETABLE_UPLOAD_BYTES = MAX_TIMETABLE_UPLOAD_MB * 1024 * 1024

DEFAULT_AUTH_SECRET_KEY = (
    "unitime-ai-development-secret-key-change-before-production-2026"
)
AUTH_SECRET_KEY = (
    os.getenv(
        "AUTH_SECRET_KEY",
        DEFAULT_AUTH_SECRET_KEY,
    ).strip()
    or DEFAULT_AUTH_SECRET_KEY
)
AUTH_ALGORITHM = "HS256"
AUTH_ACCESS_TOKEN_MINUTES = _positive_int_env(
    "AUTH_ACCESS_TOKEN_MINUTES",
    60,
)

# Compatibility registration is useful for local demos, but production access
# must always be created by an authorized institutional operator.
ALLOW_PUBLIC_STUDENT_REGISTRATION = _boolean_env(
    "ALLOW_PUBLIC_STUDENT_REGISTRATION",
    not IS_PRODUCTION,
)

APP_TIMEZONE = os.getenv(
    "APP_TIMEZONE",
    "Asia/Karachi",
).strip() or "Asia/Karachi"


CANDIDATE_RANKER_MODE = os.getenv(
    "CANDIDATE_RANKER_MODE",
    "experimental_catboost",
).strip().lower()

if CANDIDATE_RANKER_MODE not in {"deterministic", "experimental_catboost"}:
    raise RuntimeError(
        "CANDIDATE_RANKER_MODE must be deterministic or experimental_catboost."
    )
