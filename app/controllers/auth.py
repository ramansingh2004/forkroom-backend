from fastapi import HTTPException, status

from app.core.exceptions import EmailAlreadyRegisteredError
from app.schemas.auth import RegisterRequest, UserResponse
from app.services.auth import AuthService


async def register_user(payload: RegisterRequest, service: AuthService) -> UserResponse:
    try:
        user = await service.register(payload)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error

    return UserResponse.model_validate(user)
