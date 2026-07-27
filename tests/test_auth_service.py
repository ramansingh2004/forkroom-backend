from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth import AuthService


async def test_register_normalizes_email_and_hashes_password() -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None
    repository.create.side_effect = lambda user: user
    service = AuthService(repository)

    user = await service.register(
        RegisterRequest(
            email="RAMAN@Example.COM",
            password="strong-password",
            display_name="Raman Singh",
        )
    )

    repository.get_by_email.assert_awaited_once_with("raman@example.com")
    assert user.email == "raman@example.com"
    assert user.password_hash != "strong-password"
    assert verify_password("strong-password", user.password_hash)


async def test_register_stops_when_email_exists() -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = User(
        email="raman@example.com",
        password_hash="existing-hash",
        display_name="Raman Singh",
    )
    service = AuthService(repository)

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register(
            RegisterRequest(
                email="raman@example.com",
                password="strong-password",
                display_name="Raman Singh",
            )
        )

    repository.create.assert_not_awaited()


async def test_login_verifies_password_and_returns_tokens() -> None:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash=hash_password("strong-password"),
        display_name="Raman Singh",
        is_active=True,
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = AuthService(repository)

    result = await service.login(
        LoginRequest(email="RAMAN@example.com", password="strong-password")
    )

    repository.get_by_email.assert_awaited_once_with("raman@example.com")
    assert result.user is user
    assert result.tokens.access_token
    assert result.tokens.refresh_token
    assert result.tokens.access_token != result.tokens.refresh_token
    assert result.tokens.access_token_expires_in == 900

    settings = get_settings()
    access_claims = jwt.decode(
        result.tokens.access_token,
        settings.jwt_access_secret,
        algorithms=["HS256"],
    )
    refresh_claims = jwt.decode(
        result.tokens.refresh_token,
        settings.jwt_refresh_secret,
        algorithms=["HS256"],
    )

    assert access_claims["sub"] == str(user.id)
    assert access_claims["type"] == "access"
    assert refresh_claims["sub"] == str(user.id)
    assert refresh_claims["type"] == "refresh"


@pytest.mark.parametrize(
    ("repository_user", "password"),
    [
        (None, "strong-password"),
        (
            User(
                email="raman@example.com",
                password_hash=hash_password("strong-password"),
                display_name="Raman Singh",
            ),
            "wrong-password",
        ),
    ],
)
async def test_login_rejects_invalid_credentials(
    repository_user: User | None,
    password: str,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = repository_user
    service = AuthService(repository)

    with pytest.raises(InvalidCredentialsError):
        await service.login(LoginRequest(email="raman@example.com", password=password))


async def test_login_rejects_inactive_account() -> None:
    user = User(
        email="raman@example.com",
        password_hash=hash_password("strong-password"),
        display_name="Raman Singh",
        is_active=False,
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = AuthService(repository)

    with pytest.raises(InactiveAccountError):
        await service.login(
            LoginRequest(
                email="raman@example.com",
                password="strong-password",
            )
        )
