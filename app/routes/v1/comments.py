from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.comment import (
    create_comment,
    delete_comment,
    list_comments,
    update_comment,
)
from app.dependencies.auth import get_current_user
from app.dependencies.comment import get_comment_service
from app.models.user import User
from app.schemas.comment import CommentCreateRequest, CommentResponse, CommentUpdateRequest
from app.services.comment import CommentService

router = APIRouter(tags=["Comments"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[CommentService, Depends(get_comment_service)]


@router.get(
    "/workspaces/{workspace_id}/decisions/{decision_id}/comments",
    response_model=list[CommentResponse],
    summary="List decision comments",
)
async def list_route(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: Service,
    proposal_id: UUID | None = None,
    objection_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CommentResponse]:
    return await list_comments(
        workspace_id,
        decision_id,
        current_user,
        service,
        proposal_id=proposal_id,
        objection_id=objection_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace_id}/decisions/{decision_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a decision comment",
)
async def create_route(
    workspace_id: UUID,
    decision_id: UUID,
    payload: CommentCreateRequest,
    current_user: CurrentUser,
    service: Service,
) -> CommentResponse:
    return await create_comment(
        workspace_id,
        decision_id,
        payload,
        current_user,
        service,
    )


@router.patch(
    "/workspaces/{workspace_id}/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Edit a comment",
)
async def update_route(
    workspace_id: UUID,
    comment_id: UUID,
    payload: CommentUpdateRequest,
    current_user: CurrentUser,
    service: Service,
) -> CommentResponse:
    return await update_comment(workspace_id, comment_id, payload, current_user, service)


@router.delete(
    "/workspaces/{workspace_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_route(
    workspace_id: UUID,
    comment_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> None:
    await delete_comment(workspace_id, comment_id, current_user, service)
