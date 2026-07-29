from uuid import UUID

from fastapi import HTTPException, status

from app.core.exceptions import (
    ActionAccessDeniedError,
    ActionAssigneeInvalidError,
    ActionInvalidTransitionError,
    ActionNotFoundError,
    DecisionImmutableError,
    DecisionNotFoundError,
    ReviewAccessDeniedError,
    ReviewConflictError,
    ReviewInvalidScheduleError,
    ReviewNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.action_review import ActionStatus
from app.models.user import User
from app.schemas.action_review import (
    ActionCreateRequest,
    ActionResponse,
    ActionTransitionRequest,
    ActionUpdateRequest,
    ReviewCreateRequest,
    ReviewResponse,
    ReviewUpdateRequest,
)
from app.services.action_review import ActionReviewService


def _raise_action_review_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, DecisionNotFoundError):
        raise HTTPException(status_code=404, detail="Decision not found") from error
    if isinstance(error, ActionNotFoundError):
        raise HTTPException(status_code=404, detail="Implementation action not found") from error
    if isinstance(error, ReviewNotFoundError):
        raise HTTPException(status_code=404, detail="Decision review not found") from error
    if isinstance(error, (ActionAccessDeniedError, ReviewAccessDeniedError)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this operation",
        ) from error
    if isinstance(error, ActionAssigneeInvalidError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The assignee must be an eligible workspace participant",
        ) from error
    if isinstance(error, DecisionImmutableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Implementation actions and reviews require a locked decision",
        ) from error
    if isinstance(error, ActionInvalidTransitionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The implementation action transition is invalid",
        ) from error
    if isinstance(error, ReviewConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The decision already has a scheduled review",
        ) from error
    if isinstance(error, ReviewInvalidScheduleError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The decision review schedule or state is invalid",
        ) from error
    raise error


async def create_action(
    workspace_id: UUID,
    decision_id: UUID,
    payload: ActionCreateRequest,
    current_user: User,
    service: ActionReviewService,
) -> ActionResponse:
    try:
        action = await service.create_action(current_user, workspace_id, decision_id, payload)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ActionResponse.model_validate(action)


async def list_actions(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: User,
    service: ActionReviewService,
    *,
    action_status: ActionStatus | None,
    assignee_id: UUID | None,
) -> list[ActionResponse]:
    try:
        actions = await service.list_actions(
            current_user,
            workspace_id,
            decision_id,
            status=action_status,
            assignee_id=assignee_id,
        )
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return [ActionResponse.model_validate(action) for action in actions]


async def get_action(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    current_user: User,
    service: ActionReviewService,
) -> ActionResponse:
    try:
        action = await service.get_action(current_user, workspace_id, decision_id, action_id)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ActionResponse.model_validate(action)


async def update_action(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    payload: ActionUpdateRequest,
    current_user: User,
    service: ActionReviewService,
) -> ActionResponse:
    try:
        action = await service.update_action(
            current_user, workspace_id, decision_id, action_id, payload
        )
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ActionResponse.model_validate(action)


async def transition_action(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    payload: ActionTransitionRequest,
    current_user: User,
    service: ActionReviewService,
) -> ActionResponse:
    try:
        action = await service.transition_action(
            current_user, workspace_id, decision_id, action_id, payload
        )
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ActionResponse.model_validate(action)


async def create_review(
    workspace_id: UUID,
    decision_id: UUID,
    payload: ReviewCreateRequest,
    current_user: User,
    service: ActionReviewService,
) -> ReviewResponse:
    try:
        review = await service.create_review(current_user, workspace_id, decision_id, payload)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ReviewResponse.model_validate(review)


async def list_reviews(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: User,
    service: ActionReviewService,
) -> list[ReviewResponse]:
    try:
        reviews = await service.list_reviews(current_user, workspace_id, decision_id)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return [ReviewResponse.model_validate(review) for review in reviews]


async def get_review(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    current_user: User,
    service: ActionReviewService,
) -> ReviewResponse:
    try:
        review = await service.get_review(current_user, workspace_id, decision_id, review_id)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ReviewResponse.model_validate(review)


async def update_review(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    payload: ReviewUpdateRequest,
    current_user: User,
    service: ActionReviewService,
) -> ReviewResponse:
    try:
        review = await service.update_review(
            current_user, workspace_id, decision_id, review_id, payload
        )
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ReviewResponse.model_validate(review)


async def cancel_review(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    current_user: User,
    service: ActionReviewService,
) -> ReviewResponse:
    try:
        review = await service.cancel_review(current_user, workspace_id, decision_id, review_id)
    except Exception as error:
        _raise_action_review_error(error)
        raise
    return ReviewResponse.model_validate(review)
