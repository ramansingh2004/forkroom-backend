from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.integration_events import build_integration_event_emitter
from app.repositories.decision import DecisionRepository
from app.repositories.integration import IntegrationRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.voting import VotingRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.voting import VotingService


def get_voting_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> VotingService:
    integrations = IntegrationRepository(session)
    return VotingService(
        VotingRepository(session),
        ObjectionRepository(session),
        ProposalRepository(session),
        DecisionRepository(session),
        WorkspaceRepository(session),
        build_integration_event_emitter(integrations),
    )
