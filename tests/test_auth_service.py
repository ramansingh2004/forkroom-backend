from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import EmailAlreadyRegisteredError
from app.core.security import verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest
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
