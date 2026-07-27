from dataclasses import dataclass

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
)
from app.core.security import TokenPair, create_token_pair, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: TokenPair


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._users = user_repository

    async def register(self, payload: RegisterRequest) -> User:
        normalized_email = payload.email.lower()
        if await self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyRegisteredError

        user = User(
            email=normalized_email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        return await self._users.create(user)

    async def login(self, payload: LoginRequest) -> LoginResult:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None or not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError

        if not user.is_active:
            raise InactiveAccountError

        return LoginResult(user=user, tokens=create_token_pair(user.id))
