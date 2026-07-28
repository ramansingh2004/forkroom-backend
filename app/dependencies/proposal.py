from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.proposal import ProposalService


def get_proposal_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> ProposalService:
    return ProposalService(
        ProposalRepository(session),
        DecisionRepository(session),
        WorkspaceRepository(session),
    )
