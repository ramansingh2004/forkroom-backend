from dataclasses import dataclass
from datetime import timedelta

from app.core.config import get_settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import (
    TokenPair,
    create_token_pair,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.refresh_token import (
    RefreshTokenRepository,
)
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: TokenPair


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_tokens: RefreshTokenRepository,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_tokens

    @staticmethod
    def _family_revocation_ttl() -> int:
        return int(timedelta(days=(get_settings().refresh_token_expire_days)).total_seconds())

    async def register(
        self,
        payload: RegisterRequest,
    ) -> User:
        normalized_email = payload.email.lower()

        if await self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyRegisteredError

        user = User(
            email=normalized_email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )

        return await self._users.create(user)

    async def login(
        self,
        payload: LoginRequest,
    ) -> LoginResult:
        user = await self._users.get_by_email(payload.email.lower())

        if user is None or not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise InvalidCredentialsError

        if not user.is_active:
            raise InactiveAccountError

        return LoginResult(
            user=user,
            tokens=create_token_pair(user.id),
        )

    async def refresh(
        self,
        payload: RefreshRequest,
    ) -> TokenPair:
        decoded = decode_refresh_token(payload.refresh_token)

        if await self._refresh_tokens.is_family_revoked(decoded.family_id):
            raise InvalidTokenError

        was_consumed = await self._refresh_tokens.consume(
            decoded.jti,
            decoded.expires_at,
        )

        if not was_consumed:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InvalidTokenError

        user = await self._users.get_by_id(decoded.user_id)

        if user is None:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InvalidTokenError

        if not user.is_active:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InactiveAccountError

        return create_token_pair(
            user.id,
            decoded.family_id,
        )

    async def logout(
        self,
        payload: LogoutRequest,
    ) -> None:
        decoded = decode_refresh_token(payload.refresh_token)

        await self._refresh_tokens.revoke_family(
            decoded.family_id,
            self._family_revocation_ttl(),
        )
