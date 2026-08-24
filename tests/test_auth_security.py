from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from backend.auth_security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.config import AUTH_ALGORITHM, AUTH_SECRET_KEY


def test_password_hash_is_not_plaintext():
    password = "SafePassword123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)


def test_wrong_password_is_rejected():
    hashed = hash_password("SafePassword123")
    assert not verify_password("WrongPassword123", hashed)


def test_access_token_round_trip():
    token = create_access_token(42, token_version=3)
    payload = decode_access_token(token)
    assert payload.user_id == 42
    assert payload.token_version == 3


def test_invalid_access_token_is_rejected():
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not-a-jwt")


def test_expired_access_token_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "5",
            "type": "access",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
        },
        AUTH_SECRET_KEY,
        algorithm=AUTH_ALGORITHM,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)
