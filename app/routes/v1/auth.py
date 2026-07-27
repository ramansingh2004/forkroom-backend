from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.controllers.auth import login_user, register_user
from app.dependencies.auth import get_auth_service
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user account",
)
async def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    return await register_user(payload, service)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate a user",
)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    return await login_user(payload, service)
