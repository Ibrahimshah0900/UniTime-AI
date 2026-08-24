from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.auth_security import InvalidAccessTokenError, decode_access_token
from backend.auth_service import get_user_by_id
from backend.auth_types import UserRole
from backend.database import get_db
from backend.models import User


bearer_scheme = HTTPBearer(auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Authentication credentials are invalid or missing.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise authentication_error()

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError:
        raise authentication_error()

    user = get_user_by_id(db, payload.user_id)
    if user is None or not user.is_active:
        raise authentication_error()

    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed_roles = frozenset(role.value for role in roles)
    if not allowed_roles:
        raise ValueError("At least one role is required.")

    def role_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return role_dependency
