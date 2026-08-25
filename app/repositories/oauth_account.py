import secrets
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    GoogleOAuthAccountConflictError,
    InactiveAccountError,
)
from app.core.security import hash_password
from app.integrations.google_oauth import GoogleProfile
from app.models.oauth_account import OAuthAccount, OAuthProvider
from app.models.user import User


class OAuthAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authenticate_google(self, profile: GoogleProfile) -> User:
        linked = await self._get_linked_user(OAuthProvider.GOOGLE, profile.subject)
        if linked is not None:
            account, linked_user = linked
            if not linked_user.is_active:
                raise InactiveAccountError
            if account.provider_email != profile.email:
                account.provider_email = profile.email
                await self._session.commit()
            return linked_user

        user = await self._get_user_by_email(profile.email)
        if user is not None and not user.is_active:
            raise InactiveAccountError

        try:
            if user is None:
                user = User(
                    email=profile.email,
                    password_hash=hash_password(secrets.token_urlsafe(48)),
                    display_name=profile.display_name,
                    avatar_url=profile.avatar_url,
                    is_active=True,
                    is_email_verified=True,
                )
                self._session.add(user)
                await self._session.flush()
            else:
                user.is_email_verified = True
                if user.avatar_url is None and profile.avatar_url is not None:
                    user.avatar_url = profile.avatar_url

            self._session.add(
                OAuthAccount(
                    user_id=user.id,
                    provider=OAuthProvider.GOOGLE,
                    provider_subject=profile.subject,
                    provider_email=profile.email,
                )
            )
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            linked = await self._get_linked_user(OAuthProvider.GOOGLE, profile.subject)
            if linked is not None:
                _, linked_user = linked
                if not linked_user.is_active:
                    raise InactiveAccountError from error
                return linked_user
            raise GoogleOAuthAccountConflictError from error

        await self._session.refresh(user)
        return user

    async def _get_linked_user(
        self,
        provider: OAuthProvider,
        subject: str,
    ) -> tuple[OAuthAccount, User] | None:
        statement = (
            select(OAuthAccount, User)
            .join(User, User.id == OAuthAccount.user_id)
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_subject == subject,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def _get_user_by_email(self, email: str) -> User | None:
        statement = select(User).where(func.lower(User.email) == email.lower())
        return cast(User | None, await self._session.scalar(statement))
