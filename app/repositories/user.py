from typing import cast

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
        return cast(User | None, await self._session.scalar(statement))

    async def create(self, user: User) -> User:
        self._session.add(user)  # add() normally only puts the model into the session.
        try:
            await (
                self._session.commit()
            )  # The actual SQL is commonly sent when SQLAlchemy do commit
        except IntegrityError as error:
            # After a failed commit, the SQLAlchemy session is in a failed transaction state.
            await self._session.rollback()
            raise EmailAlreadyRegisteredError from error

        await self._session.refresh(user)
        return user
