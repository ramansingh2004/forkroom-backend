from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.controllers.auth import (
    forgot_password,
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
    request_email_verification,
    reset_password,
    verify_email,
)
from app.dependencies.auth import (
    enforce_auth_rate_limit,
    get_auth_service,
    get_current_user,
)
from app.models.user import User
from app.schemas.auth import (
    ActionTokenRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
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


@router.post(
    "/email-verification/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a new email verification link",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def request_verification(
    payload: EmailVerificationRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> MessageResponse:
    return await request_email_verification(payload, service)


@router.post(
    "/email-verification/confirm",
    response_model=MessageResponse,
    summary="Verify an email address",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def confirm_verification(
    payload: ActionTokenRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> MessageResponse:
    return await verify_email(payload, service)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def request_password_reset(
    payload: ForgotPasswordRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> MessageResponse:
    return await forgot_password(payload, service)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Set a new password using a reset token",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def confirm_password_reset(
    payload: ResetPasswordRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> MessageResponse:
    return await reset_password(payload, service)
