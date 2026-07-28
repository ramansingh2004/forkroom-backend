from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.objection import ObjectionService


def get_objection_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> ObjectionService:
    return ObjectionService(
        ObjectionRepository(session),
        ProposalRepository(session),
        DecisionRepository(session),
        WorkspaceRepository(session),
    )
