from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.workspace import WorkspaceService


def get_workspace_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> WorkspaceService:
    return WorkspaceService(
        WorkspaceRepository(session),
        UserRepository(session),
    )
