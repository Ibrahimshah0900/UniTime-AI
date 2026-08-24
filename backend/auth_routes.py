from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth_dependencies import get_current_user
from backend.auth_schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from backend.auth_security import access_token_lifetime_seconds, create_access_token
from backend.auth_service import authenticate_user, create_student_account
from backend.database import get_db
from backend.models import User


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register_student(request: RegisterRequest, db: Session = Depends(get_db)) -> User:
    return create_student_account(db, request)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, email=request.email, password=request.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in_seconds=access_token_lifetime_seconds(),
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
