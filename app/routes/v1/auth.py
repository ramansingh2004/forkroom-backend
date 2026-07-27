from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.controllers.auth import register_user
from app.dependencies.auth import get_auth_service
from app.schemas.auth import RegisterRequest, UserResponse
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
