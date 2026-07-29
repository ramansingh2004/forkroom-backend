from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.decision import DecisionRepository
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.voting import VotingRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.decision_lock import DecisionLockService
from app.services.voting import VotingService


def get_decision_lock_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DecisionLockService:
    decisions = DecisionRepository(session)
    objections = ObjectionRepository(session)
    proposals = ProposalRepository(session)
    voting = VotingRepository(session)
    workspaces = WorkspaceRepository(session)
    voting_service = VotingService(
        voting,
        objections,
        proposals,
        decisions,
        workspaces,
    )
    return DecisionLockService(
        DecisionLockRepository(session),
        decisions,
        proposals,
        objections,
        workspaces,
        voting_service,
    )
