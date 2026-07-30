from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.collaboration import CollaborationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.collaboration import CollaborationService


def get_collaboration_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CollaborationService:
    return CollaborationService(
        CollaborationRepository(session),
        ProposalRepository(session),
        DecisionRepository(session),
        WorkspaceRepository(session),
    )
