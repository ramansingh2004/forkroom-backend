from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.meeting import MeetingService


def get_meeting_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeetingService:
    return MeetingService(DecisionRepository(session), WorkspaceRepository(session))
