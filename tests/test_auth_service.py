from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InactiveAccountError,
    InvalidActionTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import (
    create_token_pair,
    hash_password,
    verify_password,
)
from app.integrations.email import EmailService
from app.models.user import User
from app.repositories.action_token import ActionTokenRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ActionTokenRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.auth import AuthService


@pytest.fixture
def refresh_tokens() -> AsyncMock:
    repository = AsyncMock(spec=RefreshTokenRepository)
    repository.is_family_revoked.return_value = False
    return repository


@pytest.fixture
def action_tokens() -> AsyncMock:
    return AsyncMock(spec=ActionTokenRepository)


@pytest.fixture
def email_service() -> AsyncMock:
    return AsyncMock(spec=EmailService)


async def test_register_normalizes_email_and_hashes_password(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None
    repository.create.side_effect = lambda user: user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

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
    action_tokens.issue.assert_awaited_once()
    email_service.send_verification_email.assert_awaited_once()


async def test_register_stops_when_email_exists(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = User(
        email="raman@example.com",
        password_hash="existing-hash",
        display_name="Raman Singh",
    )
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register(
            RegisterRequest(
                email="raman@example.com",
                password="strong-password",
                display_name="Raman Singh",
            )
        )

    repository.create.assert_not_awaited()


async def test_login_verifies_password_and_returns_tokens(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash=hash_password("strong-password"),
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=True,
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

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
    assert access_claims["ver"] == 0
    assert refresh_claims["ver"] == 0


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
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = repository_user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(LoginRequest(email="raman@example.com", password=password))


async def test_login_rejects_inactive_account(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    user = User(
        email="raman@example.com",
        password_hash=hash_password("strong-password"),
        display_name="Raman Singh",
        is_active=False,
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(InactiveAccountError):
        await service.login(
            LoginRequest(
                email="raman@example.com",
                password="strong-password",
            )
        )


async def test_refresh_rejects_reused_token() -> None:
    user_id = uuid4()
    tokens = create_token_pair(user_id)

    repository = AsyncMock(spec=UserRepository)
    refresh_tokens = AsyncMock(spec=RefreshTokenRepository)
    action_tokens = AsyncMock(spec=ActionTokenRepository)
    email_service = AsyncMock(spec=EmailService)

    # The token family has not already been revoked.
    refresh_tokens.is_family_revoked.return_value = False

    # False means this refresh token was already consumed.
    refresh_tokens.consume.return_value = False

    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(InvalidTokenError):
        await service.refresh(
            RefreshRequest(
                refresh_token=tokens.refresh_token,
            )
        )

    refresh_tokens.consume.assert_awaited_once()
    refresh_tokens.revoke_family.assert_awaited_once()
    repository.get_by_id.assert_not_awaited()


async def test_login_rejects_unverified_email(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    user = User(
        email="raman@example.com",
        password_hash=hash_password("strong-password"),
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=False,
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(EmailNotVerifiedError):
        await service.login(
            LoginRequest(
                email="raman@example.com",
                password="strong-password",
            )
        )


async def test_verify_email_consumes_token_and_updates_user(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="password-hash",
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=False,
    )
    repository = AsyncMock(spec=UserRepository)
    action_tokens.consume.return_value = user.id
    repository.get_by_id.return_value = user
    repository.mark_email_verified.return_value = user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    await service.verify_email(ActionTokenRequest(token="x" * 32))

    action_tokens.consume.assert_awaited_once_with(
        "email-verification",
        "x" * 32,
    )
    repository.mark_email_verified.assert_awaited_once_with(user)


async def test_verify_email_rejects_invalid_token(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    action_tokens.consume.return_value = None
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    with pytest.raises(InvalidActionTokenError):
        await service.verify_email(ActionTokenRequest(token="x" * 32))

    repository.get_by_id.assert_not_awaited()


async def test_forgot_password_does_not_reveal_missing_account(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    await service.forgot_password(ForgotPasswordRequest(email="missing@example.com"))

    action_tokens.issue.assert_not_awaited()
    email_service.send_password_reset_email.assert_not_awaited()


async def test_reset_password_hashes_password_and_increments_auth_version(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash=hash_password("old-password"),
        display_name="Raman Singh",
        is_active=True,
        auth_version=2,
    )
    repository = AsyncMock(spec=UserRepository)
    action_tokens.consume.return_value = user.id
    repository.get_by_id.return_value = user
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    await service.reset_password(
        ResetPasswordRequest(
            token="x" * 32,
            new_password="new-strong-password",
        )
    )

    repository.update_password.assert_awaited_once()
    password_hash = repository.update_password.await_args.args[1]
    assert verify_password("new-strong-password", password_hash)


async def test_request_email_verification_ignores_verified_account(
    refresh_tokens: AsyncMock,
    action_tokens: AsyncMock,
    email_service: AsyncMock,
) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="password-hash",
        display_name="Raman Singh",
        is_email_verified=True,
    )
    service = AuthService(
        repository,
        refresh_tokens,
        action_tokens,
        email_service,
    )

    await service.request_email_verification(EmailVerificationRequest(email="raman@example.com"))

    action_tokens.issue.assert_not_awaited()
