from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmailAlreadyRegisteredError
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(func.lower(User.email) == email.lower())
        return cast(
            User | None,
            await self._session.scalar(statement),
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def create(self, user: User) -> User:
        self._session.add(user)

        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError from error

        await self._session.refresh(user)
        return user

    async def mark_email_verified(self, user: User) -> User:
        user.is_email_verified = True
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_password(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        user.auth_version = (user.auth_version or 0) + 1
        await self._session.commit()
        await self._session.refresh(user)
        return user
