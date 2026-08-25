from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.redis import get_redis
from app.integrations.google_oauth import GoogleOAuthClient
from app.repositories.auth_oauth import AuthOAuthStateRepository
from app.repositories.oauth_account import OAuthAccountRepository
from app.services.google_oauth import GoogleOAuthService


def get_google_oauth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> GoogleOAuthService:
    settings = get_settings()
    return GoogleOAuthService(
        OAuthAccountRepository(session),
        AuthOAuthStateRepository(redis),
        GoogleOAuthClient(settings),
        settings,
    )
