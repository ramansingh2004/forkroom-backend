from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import EmailAlreadyRegisteredError
from app.dependencies.auth import get_auth_service
from app.main import app
from app.models.user import User


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
