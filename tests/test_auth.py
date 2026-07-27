from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
)
from app.core.security import TokenPair
from app.dependencies.auth import get_auth_service
from app.main import app
from app.models.user import User
from app.services.auth import LoginResult


@pytest.fixture
def auth_service() -> AsyncMock:
    service = AsyncMock()
    app.dependency_overrides[get_auth_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_auth_service, None)


async def test_register_returns_created_user(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    user_id = uuid4()
    auth_service.register.return_value = User(
        id=user_id,
        email="raman@example.com",
        password_hash="not-returned",
        display_name="Raman Singh",
        avatar_url=None,
        is_active=True,
        is_email_verified=False,
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "RAMAN@example.com",
            "password": "strong-password",
            "display_name": "  Raman   Singh  ",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(user_id),
        "email": "raman@example.com",
        "display_name": "Raman Singh",
        "avatar_url": None,
        "is_active": True,
        "is_email_verified": False,
        "created_at": "2026-07-26T00:00:00Z",
    }
    assert "password" not in response.text


async def test_register_rejects_duplicate_email(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    auth_service.register.side_effect = EmailAlreadyRegisteredError

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "raman@example.com",
            "password": "strong-password",
            "display_name": "Raman Singh",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists"}


async def test_register_validates_request(client: AsyncClient, auth_service: AsyncMock) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "short",
            "display_name": "R",
        },
    )

    assert response.status_code == 422
    auth_service.register.assert_not_awaited()


async def test_login_returns_user_and_tokens(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    user_id = uuid4()
    user = User(
        id=user_id,
        email="raman@example.com",
        password_hash="not-returned",
        display_name="Raman Singh",
        avatar_url=None,
        is_active=True,
        is_email_verified=False,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    auth_service.login.return_value = LoginResult(
        user=user,
        tokens=TokenPair(
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_in=900,
        ),
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "raman@example.com", "password": "strong-password"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": str(user_id),
            "email": "raman@example.com",
            "display_name": "Raman Singh",
            "avatar_url": None,
            "is_active": True,
            "is_email_verified": False,
            "created_at": "2026-07-27T00:00:00Z",
        },
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "token_type": "bearer",
        "expires_in": 900,
    }
    assert "not-returned" not in response.text


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (InvalidCredentialsError(), 401, "Invalid email or password"),
        (InactiveAccountError(), 403, "This account is inactive"),
    ],
)
async def test_login_maps_authentication_errors(
    client: AsyncClient,
    auth_service: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    auth_service.login.side_effect = service_error

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "raman@example.com", "password": "wrong-password"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
