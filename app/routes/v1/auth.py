from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.controllers.auth import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
)
from app.dependencies.auth import (
    enforce_auth_rate_limit,
    get_auth_service,
    get_current_user,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user account",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> UserResponse:
    return await register_user(
        payload,
        service,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate a user",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def login(
    payload: LoginRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> LoginResponse:
    return await login_user(
        payload,
        service,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary=("Rotate an authentication token pair"),
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def refresh(
    payload: RefreshRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> TokenResponse:
    return await refresh_tokens(
        payload,
        service,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=("Revoke the current authentication session"),
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def logout(
    payload: LogoutRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> None:
    await logout_user(
        payload,
        service,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user",
)
async def get_me(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UserResponse:
    return UserResponse.model_validate(current_user)
