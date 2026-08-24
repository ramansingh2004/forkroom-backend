from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.controllers.mention import (
    list_mentions,
    mark_all_read,
    mark_read,
    mark_unread,
    unread_count,
)
from app.dependencies.auth import get_current_user
from app.dependencies.mention import get_mention_service
from app.models.user import User
from app.schemas.mention import (
    MentionListResponse,
    MentionMarkAllReadResponse,
    MentionReadResponse,
    MentionStatus,
    MentionUnreadCountResponse,
)
from app.services.mention import MentionService

router = APIRouter(tags=["Mentions"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[MentionService, Depends(get_mention_service)]


@router.get(
    "/workspaces/{workspace_id}/mentions",
    response_model=MentionListResponse,
    summary="List my workspace mentions",
)
async def list_route(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: Service,
    mention_status: Annotated[MentionStatus, Query(alias="status")] = MentionStatus.ALL,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: str | None = None,
) -> MentionListResponse:
    return await list_mentions(
        workspace_id,
        current_user,
        service,
        mention_status=mention_status,
        limit=limit,
        cursor=cursor,
    )


@router.patch(
    "/workspaces/{workspace_id}/mentions/{mention_id}/read",
    response_model=MentionReadResponse,
    summary="Mark a mention as read",
)
async def mark_read_route(
    workspace_id: UUID,
    mention_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> MentionReadResponse:
    return await mark_read(workspace_id, mention_id, current_user, service)


@router.delete(
    "/workspaces/{workspace_id}/mentions/{mention_id}/read",
    response_model=MentionReadResponse,
    summary="Mark a mention as unread",
)
async def mark_unread_route(
    workspace_id: UUID,
    mention_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> MentionReadResponse:
    return await mark_unread(workspace_id, mention_id, current_user, service)


@router.post(
    "/workspaces/{workspace_id}/mentions/read-all",
    response_model=MentionMarkAllReadResponse,
    summary="Mark all my workspace mentions as read",
)
async def mark_all_read_route(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> MentionMarkAllReadResponse:
    return await mark_all_read(workspace_id, current_user, service)


@router.get(
    "/mentions/unread-count",
    response_model=MentionUnreadCountResponse,
    summary="Get my global unread mention count",
)
async def unread_count_route(
    current_user: CurrentUser,
    service: Service,
) -> MentionUnreadCountResponse:
    return await unread_count(current_user, service)
