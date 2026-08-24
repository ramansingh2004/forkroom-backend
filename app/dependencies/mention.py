from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.mention import MentionRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.mention import MentionService


def get_mention_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MentionService:
    return MentionService(
        MentionRepository(session),
        WorkspaceRepository(session),
    )
