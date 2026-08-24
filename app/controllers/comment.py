from uuid import UUID

from fastapi import HTTPException, status

from app.core.exceptions import (
    CommentAccessDeniedError,
    CommentContextInvalidError,
    CommentNotFoundError,
    DecisionNotFoundError,
    MentionMemberInvalidError,
    WorkspaceNotFoundError,
)
from app.models.user import User
from app.repositories.comment import CommentRecord
from app.schemas.comment import (
    CommentAuthorResponse,
    CommentCreateRequest,
    CommentResponse,
    CommentUpdateRequest,
    StructuredCommentBody,
)
from app.services.comment import CommentService


def _raise_comment_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, DecisionNotFoundError):
        raise HTTPException(status_code=404, detail="Decision not found") from error
    if isinstance(error, CommentNotFoundError):
        raise HTTPException(status_code=404, detail="Comment not found") from error
    if isinstance(error, CommentContextInvalidError):
        raise HTTPException(
            status_code=404,
            detail="Comment context not found in this decision",
        ) from error
    if isinstance(error, CommentAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to change this comment",
        ) from error
    if isinstance(error, MentionMemberInvalidError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Every mentioned user must be an active member of this workspace",
        ) from error
    raise error


def _response(record: CommentRecord) -> CommentResponse:
    return CommentResponse(
        id=record.comment.id,
        workspace_id=record.comment.workspace_id,
        decision_id=record.comment.decision_id,
        proposal_id=record.comment.proposal_id,
        objection_id=record.comment.objection_id,
        author=CommentAuthorResponse(
            id=record.author.id,
            display_name=record.author.display_name,
            avatar_url=record.author.avatar_url,
        ),
        body=record.comment.body,
        structured_body=StructuredCommentBody.model_validate(record.comment.structured_body),
        created_at=record.comment.created_at,
        updated_at=record.comment.updated_at,
    )


async def list_comments(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: User,
    service: CommentService,
    *,
    proposal_id: UUID | None,
    objection_id: UUID | None,
    limit: int,
    offset: int,
) -> list[CommentResponse]:
    try:
        records = await service.list_comments(
            current_user,
            workspace_id,
            decision_id,
            proposal_id=proposal_id,
            objection_id=objection_id,
            limit=limit,
            offset=offset,
        )
    except Exception as error:
        _raise_comment_error(error)
        raise
    return [_response(record) for record in records]


async def create_comment(
    workspace_id: UUID,
    decision_id: UUID,
    payload: CommentCreateRequest,
    current_user: User,
    service: CommentService,
) -> CommentResponse:
    try:
        record = await service.create(current_user, workspace_id, decision_id, payload)
    except Exception as error:
        _raise_comment_error(error)
        raise
    return _response(record)


async def update_comment(
    workspace_id: UUID,
    comment_id: UUID,
    payload: CommentUpdateRequest,
    current_user: User,
    service: CommentService,
) -> CommentResponse:
    try:
        record = await service.update(current_user, workspace_id, comment_id, payload)
    except Exception as error:
        _raise_comment_error(error)
        raise
    return _response(record)


async def delete_comment(
    workspace_id: UUID,
    comment_id: UUID,
    current_user: User,
    service: CommentService,
) -> None:
    try:
        await service.delete(current_user, workspace_id, comment_id)
    except Exception as error:
        _raise_comment_error(error)
