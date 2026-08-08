from fastapi import HTTPException, status

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InactiveAccountError,
    InvalidActionTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import TokenPair
from app.schemas.auth import (
    ActionTokenRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.services.auth import AuthService, LoginResult


async def register_user(
    payload: RegisterRequest,
    service: AuthService,
) -> UserResponse:
    try:
        user = await service.register(payload)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("An account with this email already exists"),
        ) from error

    return UserResponse.model_validate(user)


async def login_user(
    payload: LoginRequest,
    service: AuthService,
) -> LoginResult:
    try:
        result = await service.login(payload)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except InactiveAccountError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from error
    except EmailNotVerifiedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before logging in",
        ) from error

    return result


async def refresh_tokens(
    payload: RefreshRequest,
    service: AuthService,
) -> TokenPair:
    try:
        tokens = await service.refresh(payload)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Invalid, expired, or already used refresh token"),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except InactiveAccountError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from error

    return tokens


async def logout_user(
    payload: LogoutRequest,
    service: AuthService,
) -> None:
    try:
        await service.logout(payload)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Invalid or expired refresh token"),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


async def request_email_verification(
    payload: EmailVerificationRequest,
    service: AuthService,
) -> MessageResponse:
    await service.request_email_verification(payload)
    return MessageResponse(
        detail="If the account can be verified, a verification email has been sent"
    )


async def verify_email(
    payload: ActionTokenRequest,
    service: AuthService,
) -> MessageResponse:
    try:
        await service.verify_email(payload)
    except InvalidActionTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification token",
        ) from error
    except InactiveAccountError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from error

    return MessageResponse(detail="Email verified successfully")


async def forgot_password(
    payload: ForgotPasswordRequest,
    service: AuthService,
) -> MessageResponse:
    await service.forgot_password(payload)
    return MessageResponse(
        detail="If an active account exists, a password reset email has been sent"
    )


async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthService,
) -> MessageResponse:
    try:
        await service.reset_password(payload)
    except InvalidActionTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        ) from error
    except InactiveAccountError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from error

    return MessageResponse(detail="Password reset successfully; sign in again on all devices")