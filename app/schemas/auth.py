from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )
    display_name: str = Field(
        min_length=2,
        max_length=100,
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(
        cls,
        value: str,
    ) -> str:
        normalized = " ".join(value.split())

        if len(normalized) < 2:
            raise ValueError("Display name must contain at least 2 characters")

        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=1,
        max_length=128,
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    avatar_url: str | None
    is_active: bool
    is_email_verified: bool
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class ActionTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(ActionTokenRequest):
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    detail: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
