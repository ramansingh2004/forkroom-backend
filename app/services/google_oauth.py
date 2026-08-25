import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from app.core.config import Settings
from app.core.exceptions import GoogleOAuthStateInvalidError
from app.core.security import TokenPair, create_token_pair
from app.integrations.google_oauth import GoogleOAuthClient
from app.models.user import User
from app.repositories.auth_oauth import AuthOAuthState, AuthOAuthStateRepository
from app.repositories.oauth_account import OAuthAccountRepository


@dataclass(frozen=True, slots=True)
class GoogleOAuthCompletion:
    user: User
    tokens: TokenPair
    redirect_url: str


class GoogleOAuthService:
    def __init__(
        self,
        accounts: OAuthAccountRepository,
        states: AuthOAuthStateRepository,
        client: GoogleOAuthClient,
        settings: Settings,
    ) -> None:
        self._accounts = accounts
        self._states = states
        self._client = client
        self._settings = settings

    async def begin(self, return_path: str) -> str:
        safe_return_path = self._safe_return_path(return_path)
        code_verifier = secrets.token_urlsafe(64)
        state = await self._states.issue(
            AuthOAuthState(
                code_verifier=code_verifier,
                return_path=safe_return_path,
            ),
            self._settings.google_oauth_state_ttl_seconds,
        )
        return self._client.authorization_url(
            state=state,
            code_challenge=self._code_challenge(code_verifier),
        )

    async def complete(self, *, code: str, state: str) -> GoogleOAuthCompletion:
        oauth_state = await self._states.consume(state)
        if oauth_state is None:
            raise GoogleOAuthStateInvalidError
        profile = await self._client.exchange_code(code, oauth_state.code_verifier)
        user = await self._accounts.authenticate_google(profile)
        tokens = create_token_pair(user.id, token_version=user.auth_version or 0)
        return GoogleOAuthCompletion(
            user=user,
            tokens=tokens,
            redirect_url=self._frontend_redirect(
                oauth_state.return_path,
                {"oauth": "google", "status": "success"},
            ),
        )

    async def cancel(self, *, state: str, provider_error: str) -> str:
        oauth_state = await self._states.consume(state)
        if oauth_state is None:
            raise GoogleOAuthStateInvalidError
        safe_error = "access_denied" if provider_error == "access_denied" else "oauth_failed"
        return self._frontend_redirect(
            oauth_state.return_path,
            {"oauth": "google", "error": safe_error},
        )

    def _frontend_redirect(self, return_path: str, query: dict[str, str]) -> str:
        separator = "&" if "?" in return_path else "?"
        return (
            f"{self._settings.frontend_url.rstrip('/')}{return_path}{separator}{urlencode(query)}"
        )

    @staticmethod
    def _safe_return_path(return_path: str) -> str:
        if len(return_path) > 2048:
            return "/"
        parsed = urlsplit(return_path)
        if (
            not return_path.startswith("/")
            or return_path.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or "\\" in return_path
        ):
            return "/"
        return return_path

    @staticmethod
    def _code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
