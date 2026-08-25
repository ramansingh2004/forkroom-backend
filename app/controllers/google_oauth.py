from fastapi import HTTPException, status

from app.core.exceptions import (
    GoogleOAuthAccountConflictError,
    GoogleOAuthNotConfiguredError,
    GoogleOAuthProfileInvalidError,
    GoogleOAuthProviderError,
    GoogleOAuthStateInvalidError,
    InactiveAccountError,
)
from app.services.google_oauth import GoogleOAuthCompletion, GoogleOAuthService


def _raise_google_oauth_error(error: Exception) -> None:
    if isinstance(error, GoogleOAuthNotConfiguredError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        ) from error
    if isinstance(error, GoogleOAuthStateInvalidError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Google sign-in state",
        ) from error
    if isinstance(error, InactiveAccountError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from error
    if isinstance(error, GoogleOAuthAccountConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Google account cannot be linked to the existing account",
        ) from error
    if isinstance(error, GoogleOAuthProfileInvalidError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return a usable verified profile",
        ) from error
    if isinstance(error, GoogleOAuthProviderError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google sign-in could not be completed",
        ) from error
    raise error


async def begin_google_oauth(return_path: str, service: GoogleOAuthService) -> str:
    try:
        return await service.begin(return_path)
    except Exception as error:
        _raise_google_oauth_error(error)
        raise


async def complete_google_oauth(
    code: str,
    state: str,
    service: GoogleOAuthService,
) -> GoogleOAuthCompletion:
    try:
        return await service.complete(code=code, state=state)
    except Exception as error:
        _raise_google_oauth_error(error)
        raise


async def cancel_google_oauth(
    state: str,
    provider_error: str,
    service: GoogleOAuthService,
) -> str:
    try:
        return await service.cancel(state=state, provider_error=provider_error)
    except Exception as error:
        _raise_google_oauth_error(error)
        raise
