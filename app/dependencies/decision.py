from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.decision import DecisionService


def get_decision_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> DecisionService:
    return DecisionService(
        DecisionRepository(session),
        WorkspaceRepository(session),
    )
