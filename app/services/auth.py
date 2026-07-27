from dataclasses import dataclass

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
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
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

        was_consumed = await self._refresh_tokens.consume(
            decoded.jti,
            decoded.expires_at,
        )

        if not was_consumed:
            raise InvalidTokenError

        user = await self._users.get_by_id(decoded.user_id)

        if user is None:
            raise InvalidTokenError

        if not user.is_active:
            raise InactiveAccountError

        return create_token_pair(user.id)
