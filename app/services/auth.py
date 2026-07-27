from app.core.exceptions import EmailAlreadyRegisteredError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest


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
