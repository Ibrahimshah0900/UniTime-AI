from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from backend.config import AUTH_ACCESS_TOKEN_MINUTES, AUTH_ALGORITHM, AUTH_SECRET_KEY


_password_hash = PasswordHash.recommended()


class InvalidAccessTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    user_id: int
    token_version: int


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(user_id: int, *, token_version: int = 0) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=AUTH_ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "ver": token_version,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenPayload:
    try:
        payload = jwt.decode(
            token,
            AUTH_SECRET_KEY,
            algorithms=[AUTH_ALGORITHM],
            options={"require": ["sub", "type", "ver", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError("Access token is invalid.") from exc

    if payload.get("type") != "access":
        raise InvalidAccessTokenError("Access token is invalid.")

    try:
        user_id = int(payload["sub"])
        token_version = int(payload["ver"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("Access token is invalid.") from exc

    if user_id < 1 or token_version < 0:
        raise InvalidAccessTokenError("Access token is invalid.")

    return AccessTokenPayload(user_id=user_id, token_version=token_version)


def access_token_lifetime_seconds() -> int:
    return AUTH_ACCESS_TOKEN_MINUTES * 60
