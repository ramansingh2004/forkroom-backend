from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InactiveAccountError,
    InvalidActionTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import TokenPair
from app.dependencies.auth import (
    enforce_auth_rate_limit,
    get_auth_service,
)
from app.main import app
from app.models.user import User
from app.services.auth import LoginResult


@pytest.fixture
def auth_service() -> Iterator[AsyncMock]:
    service = AsyncMock()

    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[enforce_auth_rate_limit] = lambda: None

    yield service

    app.dependency_overrides.pop(get_auth_service, None)
    app.dependency_overrides.pop(enforce_auth_rate_limit, None)


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


async def test_login_returns_user_and_sets_auth_cookies(
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
        }
    }
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text
    assert "not-returned" not in response.text
    set_cookies = response.headers.get_list("set-cookie")
    assert any(
        "forkroom_access=access-token" in cookie and "HttpOnly" in cookie for cookie in set_cookies
    )
    assert any(
        "forkroom_refresh=refresh-token" in cookie and "HttpOnly" in cookie
        for cookie in set_cookies
    )


async def test_refresh_rotates_tokens_from_cookie(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    auth_service.refresh.return_value = TokenPair(
        access_token="new-access-token",
        refresh_token="new-refresh-token",
        access_token_expires_in=900,
    )
    client.cookies.set(
        "forkroom_refresh",
        "old-refresh-token",
        path="/api/v1/auth",
    )

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 204
    assert response.content == b""
    refresh_request = auth_service.refresh.await_args.args[0]
    assert refresh_request.refresh_token == "old-refresh-token"
    set_cookies = response.headers.get_list("set-cookie")
    assert any("forkroom_access=new-access-token" in cookie for cookie in set_cookies)
    assert any("forkroom_refresh=new-refresh-token" in cookie for cookie in set_cookies)


async def test_refresh_requires_refresh_cookie(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    client.cookies.clear()

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing refresh token"}
    auth_service.refresh.assert_not_awaited()


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (InvalidCredentialsError(), 401, "Invalid email or password"),
        (InactiveAccountError(), 403, "This account is inactive"),
        (EmailNotVerifiedError(), 403, "Verify your email before logging in"),
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


async def test_logout_revokes_session(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    client.cookies.set("forkroom_access", "access-token", path="/")
    client.cookies.set(
        "forkroom_refresh",
        "valid-refresh-token",
        path="/api/v1/auth",
    )

    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    auth_service.logout.assert_awaited_once()
    logout_request = auth_service.logout.await_args.args[0]
    assert logout_request.refresh_token == "valid-refresh-token"
    set_cookies = response.headers.get_list("set-cookie")
    assert any("forkroom_access=" in cookie and "Max-Age=0" in cookie for cookie in set_cookies)
    assert any("forkroom_refresh=" in cookie and "Max-Age=0" in cookie for cookie in set_cookies)


async def test_logout_rejects_invalid_refresh_token(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    auth_service.logout.side_effect = InvalidTokenError
    client.cookies.set(
        "forkroom_refresh",
        "invalid-refresh-token",
        path="/api/v1/auth",
    )

    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    set_cookies = response.headers.get_list("set-cookie")
    assert any("forkroom_refresh=" in cookie and "Max-Age=0" in cookie for cookie in set_cookies)


async def test_request_email_verification_uses_generic_response(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    response = await client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "raman@example.com"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If the account can be verified, a verification email has been sent"
    }
    auth_service.request_email_verification.assert_awaited_once()


async def test_confirm_email_verification(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    response = await client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": "x" * 32},
    )

    assert response.status_code == 200
    assert response.json() == {"detail": "Email verified successfully"}
    auth_service.verify_email.assert_awaited_once()


async def test_confirm_email_verification_rejects_invalid_token(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    auth_service.verify_email.side_effect = InvalidActionTokenError

    response = await client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": "x" * 32},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired email verification token"}


async def test_forgot_password_uses_generic_response(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "raman@example.com"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If an active account exists, a password reset email has been sent"
    }
    auth_service.forgot_password.assert_awaited_once()


async def test_reset_password(
    client: AsyncClient,
    auth_service: AsyncMock,
) -> None:
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "x" * 32,
            "new_password": "new-strong-password",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "detail": "Password reset successfully; sign in again on all devices"
    }
    auth_service.reset_password.assert_awaited_once()
