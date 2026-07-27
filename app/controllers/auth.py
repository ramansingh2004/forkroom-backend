from fastapi import HTTPException, status

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidTokenError,
)
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
) -> LoginResponse:
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

    return LoginResponse(
        user=UserResponse.model_validate(result.user),
        access_token=(result.tokens.access_token),
        refresh_token=(result.tokens.refresh_token),
        expires_in=(result.tokens.access_token_expires_in),
    )


async def refresh_tokens(
    payload: RefreshRequest,
    service: AuthService,
) -> TokenResponse:
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

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=(tokens.access_token_expires_in),
    )


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
