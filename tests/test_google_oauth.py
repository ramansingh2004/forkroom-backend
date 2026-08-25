import base64
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.exceptions import (
    GoogleOAuthProfileInvalidError,
    GoogleOAuthStateInvalidError,
)
from app.core.security import TokenPair
from app.dependencies.auth import enforce_auth_rate_limit
from app.dependencies.google_oauth import get_google_oauth_service
from app.integrations.google_oauth import GoogleOAuthClient, GoogleProfile
from app.main import app
from app.models.oauth_account import OAuthAccount, OAuthProvider
from app.models.user import User
from app.repositories.auth_oauth import AuthOAuthState, AuthOAuthStateRepository
from app.repositories.oauth_account import OAuthAccountRepository
from app.services.google_oauth import (
    GoogleOAuthCompletion,
    GoogleOAuthService,
)


def google_settings() -> Settings:
    return Settings(
        google_oauth_client_id="client.apps.googleusercontent.com",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="http://localhost:8000/api/v1/auth/google/callback",
        frontend_url="http://localhost:3000",
    )


def make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="not-returned",
        display_name="Raman Singh",
        avatar_url="https://example.com/avatar.png",
        is_active=True,
        is_email_verified=True,
        auth_version=0,
        created_at=now,
        updated_at=now,
    )


class ExecuteResult:
    def __init__(self, row: tuple[OAuthAccount, User] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[OAuthAccount, User] | None:
        return self._row


def test_google_authorization_url_uses_code_pkce_and_oidc_scopes() -> None:
    url = GoogleOAuthClient(google_settings()).authorization_url(
        state="opaque-state",
        code_challenge="challenge",
    )
    query = parse_qs(urlparse(url).query)

    assert query["response_type"] == ["code"]
    assert query["state"] == ["opaque-state"]
    assert query["code_challenge"] == ["challenge"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email profile"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/v1/auth/google/callback"]


@pytest.mark.asyncio
async def test_google_code_exchange_returns_verified_profile() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url == GoogleOAuthClient.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "google-access-token"})
        assert request.headers["authorization"] == "Bearer google-access-token"
        return httpx.Response(
            200,
            json={
                "sub": "stable-google-subject",
                "email": "RAMAN@example.com",
                "email_verified": True,
                "name": "Raman Singh",
                "picture": "https://example.com/avatar.png",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        profile = await GoogleOAuthClient(google_settings(), http).exchange_code(
            "authorization-code",
            "pkce-verifier",
        )

    assert profile.subject == "stable-google-subject"
    assert profile.email == "raman@example.com"
    assert profile.email_verified is True
    assert b"code_verifier=pkce-verifier" in requests[0].content


@pytest.mark.asyncio
async def test_google_code_exchange_rejects_unverified_email() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == GoogleOAuthClient.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(
            200,
            json={
                "sub": "subject",
                "email": "raman@example.com",
                "email_verified": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(GoogleOAuthProfileInvalidError):
            await GoogleOAuthClient(google_settings(), http).exchange_code("code", "verifier")


@pytest.mark.asyncio
async def test_auth_oauth_state_is_stored_with_ttl() -> None:
    redis = AsyncMock()
    repository = AuthOAuthStateRepository(redis)

    state = await repository.issue(
        AuthOAuthState(code_verifier="verifier", return_path="/decisions"),
        600,
    )

    assert len(state) >= 32
    key, value = redis.set.await_args.args
    assert key == f"auth:google:oauth-state:{state}"
    assert json.loads(value) == {
        "code_verifier": "verifier",
        "return_path": "/decisions",
    }
    assert redis.set.await_args.kwargs == {"ex": 600}


@pytest.mark.asyncio
async def test_auth_oauth_state_is_consumed_once() -> None:
    redis = AsyncMock()
    redis.eval.return_value = json.dumps({"code_verifier": "verifier", "return_path": "/decisions"})
    repository = AuthOAuthStateRepository(redis)

    result = await repository.consume("state")

    assert result == AuthOAuthState(code_verifier="verifier", return_path="/decisions")
    assert redis.eval.await_args.args[2] == "auth:google:oauth-state:state"


@pytest.mark.asyncio
async def test_google_login_links_verified_email_to_existing_user() -> None:
    user = make_user()
    user.is_email_verified = False
    user.avatar_url = None
    session = Mock()
    session.execute = AsyncMock(return_value=ExecuteResult(None))
    session.scalar = AsyncMock(return_value=user)
    session.add = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    repository = OAuthAccountRepository(session)
    profile = GoogleProfile(
        subject="google-subject",
        email=user.email,
        email_verified=True,
        display_name=user.display_name,
        avatar_url="https://example.com/google-avatar.png",
    )

    result = await repository.authenticate_google(profile)

    assert result is user
    assert user.is_email_verified is True
    assert user.avatar_url == "https://example.com/google-avatar.png"
    account = session.add.call_args.args[0]
    assert isinstance(account, OAuthAccount)
    assert account.provider is OAuthProvider.GOOGLE
    assert account.provider_subject == "google-subject"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_login_creates_user_without_storing_google_token() -> None:
    session = Mock()
    session.execute = AsyncMock(return_value=ExecuteResult(None))
    session.scalar = AsyncMock(return_value=None)
    session.add = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()

    async def flush() -> None:
        created_user = session.add.call_args_list[0].args[0]
        created_user.id = uuid4()

    session.flush = AsyncMock(side_effect=flush)
    repository = OAuthAccountRepository(session)
    profile = GoogleProfile(
        subject="google-subject",
        email="new@example.com",
        email_verified=True,
        display_name="New User",
        avatar_url=None,
    )

    user = await repository.authenticate_google(profile)

    assert user.email == "new@example.com"
    assert user.is_email_verified is True
    assert user.password_hash
    account = session.add.call_args_list[1].args[0]
    assert isinstance(account, OAuthAccount)
    assert not hasattr(account, "access_token")


@pytest.mark.asyncio
async def test_google_oauth_begin_generates_matching_pkce() -> None:
    accounts = Mock()
    states = Mock()
    states.issue = AsyncMock(return_value="state")
    client = Mock()
    client.authorization_url.return_value = "https://accounts.google.com/authorize"
    service = GoogleOAuthService(accounts, states, client, google_settings())

    url = await service.begin("/w/workspace")

    issued = states.issue.await_args.args[0]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(issued.code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert issued.return_path == "/w/workspace"
    client.authorization_url.assert_called_once_with(state="state", code_challenge=expected)
    assert url == "https://accounts.google.com/authorize"


@pytest.mark.asyncio
async def test_google_oauth_blocks_external_return_url() -> None:
    states = Mock()
    states.issue = AsyncMock(return_value="state")
    client = Mock()
    client.authorization_url.return_value = "https://accounts.google.com/authorize"
    service = GoogleOAuthService(Mock(), states, client, google_settings())

    await service.begin("https://evil.example/steal")

    assert states.issue.await_args.args[0].return_path == "/"


@pytest.mark.asyncio
async def test_google_oauth_completion_uses_subject_profile_and_issues_tokens() -> None:
    user = make_user()
    states = Mock()
    states.consume = AsyncMock(
        return_value=AuthOAuthState(code_verifier="verifier", return_path="/decisions")
    )
    profile = GoogleProfile(
        subject="google-subject",
        email=user.email,
        email_verified=True,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
    )
    client = Mock()
    client.exchange_code = AsyncMock(return_value=profile)
    accounts = Mock()
    accounts.authenticate_google = AsyncMock(return_value=user)
    service = GoogleOAuthService(accounts, states, client, google_settings())

    result = await service.complete(code="code", state="state")

    client.exchange_code.assert_awaited_once_with("code", "verifier")
    accounts.authenticate_google.assert_awaited_once_with(profile)
    assert result.user is user
    assert result.tokens.access_token
    assert result.redirect_url == ("http://localhost:3000/decisions?oauth=google&status=success")


@pytest.mark.asyncio
async def test_google_oauth_rejects_expired_state_before_contacting_google() -> None:
    states = Mock()
    states.consume = AsyncMock(return_value=None)
    client = Mock()
    service = GoogleOAuthService(Mock(), states, client, google_settings())

    with pytest.raises(GoogleOAuthStateInvalidError):
        await service.complete(code="code", state="expired")

    client.exchange_code.assert_not_called()


@pytest.fixture
def google_oauth_api() -> Iterator[tuple[AsyncMock, User]]:
    service = AsyncMock()
    user = make_user()
    service.begin.return_value = "https://accounts.google.com/o/oauth2/v2/auth?state=state"
    service.complete.return_value = GoogleOAuthCompletion(
        user=user,
        tokens=TokenPair(
            access_token="forkroom-access",
            refresh_token="forkroom-refresh",
            access_token_expires_in=900,
        ),
        redirect_url="http://localhost:3000/?oauth=google&status=success",
    )
    service.cancel.return_value = "http://localhost:3000/?oauth=google&error=access_denied"
    app.dependency_overrides[get_google_oauth_service] = lambda: service
    app.dependency_overrides[enforce_auth_rate_limit] = lambda: None
    yield service, user
    app.dependency_overrides.pop(get_google_oauth_service, None)
    app.dependency_overrides.pop(enforce_auth_rate_limit, None)


@pytest.mark.asyncio
async def test_google_authorize_route_redirects_to_google(
    client: AsyncClient,
    google_oauth_api: tuple[AsyncMock, User],
) -> None:
    response = await client.get(
        "/api/v1/auth/google/authorize?return_path=/decisions",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com/")
    google_oauth_api[0].begin.assert_awaited_once_with("/decisions")


@pytest.mark.asyncio
async def test_google_callback_sets_forkroom_cookies_and_redirects(
    client: AsyncClient,
    google_oauth_api: tuple[AsyncMock, User],
) -> None:
    response = await client.get(
        "/api/v1/auth/google/callback?code=code&state=state",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == ("http://localhost:3000/?oauth=google&status=success")
    cookies = response.headers.get_list("set-cookie")
    assert any("forkroom_access=forkroom-access" in cookie for cookie in cookies)
    assert any("forkroom_refresh=forkroom-refresh" in cookie for cookie in cookies)


@pytest.mark.asyncio
async def test_google_denial_consumes_state_and_returns_to_frontend(
    client: AsyncClient,
    google_oauth_api: tuple[AsyncMock, User],
) -> None:
    response = await client.get(
        "/api/v1/auth/google/callback?error=access_denied&state=state",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("oauth=google&error=access_denied")
    google_oauth_api[0].cancel.assert_awaited_once_with(
        state="state",
        provider_error="access_denied",
    )
