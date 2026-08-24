from uuid import UUID

from fastapi import HTTPException

from app.core.exceptions import (
    MentionCursorInvalidError,
    MentionNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.user import User
from app.schemas.mention import (
    MentionListResponse,
    MentionMarkAllReadResponse,
    MentionReadResponse,
    MentionStatus,
    MentionUnreadCountResponse,
)
from app.services.mention import MentionService


def _raise_mention_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, MentionNotFoundError):
        raise HTTPException(status_code=404, detail="Mention not found") from error
    if isinstance(error, MentionCursorInvalidError):
        raise HTTPException(status_code=400, detail="Invalid mentions cursor") from error
    raise error


async def list_mentions(
    workspace_id: UUID,
    current_user: User,
    service: MentionService,
    *,
    mention_status: MentionStatus,
    limit: int,
    cursor: str | None,
) -> MentionListResponse:
    try:
        return await service.list_mentions(
            current_user,
            workspace_id,
            status=mention_status,
            limit=limit,
            cursor=cursor,
        )
    except Exception as error:
        _raise_mention_error(error)
        raise


async def mark_read(
    workspace_id: UUID,
    mention_id: UUID,
    current_user: User,
    service: MentionService,
) -> MentionReadResponse:
    try:
        mention = await service.mark_read(current_user, workspace_id, mention_id)
    except Exception as error:
        _raise_mention_error(error)
        raise
    return MentionReadResponse(id=mention.id, read_at=mention.read_at)


async def mark_unread(
    workspace_id: UUID,
    mention_id: UUID,
    current_user: User,
    service: MentionService,
) -> MentionReadResponse:
    try:
        mention = await service.mark_unread(current_user, workspace_id, mention_id)
    except Exception as error:
        _raise_mention_error(error)
        raise
    return MentionReadResponse(id=mention.id, read_at=mention.read_at)


async def mark_all_read(
    workspace_id: UUID,
    current_user: User,
    service: MentionService,
) -> MentionMarkAllReadResponse:
    try:
        updated = await service.mark_all_read(current_user, workspace_id)
    except Exception as error:
        _raise_mention_error(error)
        raise
    return MentionMarkAllReadResponse(updated=updated)


async def unread_count(
    current_user: User,
    service: MentionService,
) -> MentionUnreadCountResponse:
    return MentionUnreadCountResponse(count=await service.unread_count(current_user))
