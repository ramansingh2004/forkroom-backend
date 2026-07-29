from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.action_review import ActionReviewRepository
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.action_review import ActionReviewService


def get_action_review_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActionReviewService:
    return ActionReviewService(
        ActionReviewRepository(session),
        DecisionRepository(session),
        WorkspaceRepository(session),
    )
