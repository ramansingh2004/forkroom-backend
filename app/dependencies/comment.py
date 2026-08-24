from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.comment import CommentRepository
from app.repositories.mention import MentionRepository
from app.services.comment import CommentService


def get_comment_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommentService:
    return CommentService(
        CommentRepository(session),
        MentionRepository(session),
    )
