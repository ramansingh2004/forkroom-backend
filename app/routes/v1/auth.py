from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

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
from app.core.config import get_settings
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
    UserResponse,
)
from app.services.auth import AuthService

ACCESS_COOKIE = "forkroom_access"
REFRESH_COOKIE = "forkroom_refresh"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    secure = settings.app_env in {"staging", "production"}
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    secure = settings.app_env in {"staging", "production"}
    response.delete_cookie(
        ACCESS_COOKIE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )


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
    response: Response,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> LoginResponse:
    result = await login_user(
        payload,
        service,
    )
    _set_auth_cookies(
        response,
        result.tokens.access_token,
        result.tokens.refresh_token,
    )
    return LoginResponse(user=UserResponse.model_validate(result.user))


@router.post(
    "/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=("Rotate an authentication token pair"),
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> None:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    tokens = await refresh_tokens(
        RefreshRequest(refresh_token=refresh_token),
        service,
    )
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=("Revoke the current authentication session"),
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
) -> None:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    try:
        if refresh_token:
            try:
                await logout_user(
                    LogoutRequest(refresh_token=refresh_token),
                    service,
                )
            except HTTPException as error:
                if error.status_code != status.HTTP_401_UNAUTHORIZED:
                    raise
    finally:
        _clear_auth_cookies(response)


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