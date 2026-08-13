from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.redis import get_redis
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.repositories.integration import IntegrationRepository
from app.repositories.integration_oauth import IntegrationOAuthStateRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.integration import IntegrationService


def get_integration_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> IntegrationService:
    settings = get_settings()
    return IntegrationService(
        IntegrationRepository(session),
        WorkspaceRepository(session),
        IntegrationOAuthStateRepository(redis),
        IntegrationProviderRegistry(settings),
        settings,
    )
