from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.action_review import (
    cancel_review,
    create_action,
    create_review,
    get_action,
    get_review,
    list_actions,
    list_reviews,
    transition_action,
    update_action,
    update_review,
)
from app.dependencies.action_review import get_action_review_service
from app.dependencies.auth import get_current_user
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

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions/{decision_id}",
)

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[ActionReviewService, Depends(get_action_review_service)]


@router.post(
    "/actions",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Implementation Actions"],
    summary="Create an owned implementation action",
)
async def create_action_route(
    workspace_id: UUID,
    decision_id: UUID,
    payload: ActionCreateRequest,
    current_user: CurrentUser,
    service: Service,
) -> ActionResponse:
    return await create_action(workspace_id, decision_id, payload, current_user, service)


@router.get(
    "/actions",
    response_model=list[ActionResponse],
    tags=["Implementation Actions"],
    summary="List implementation actions",
)
async def list_actions_route(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: Service,
    action_status: Annotated[ActionStatus | None, Query(alias="status")] = None,
    assignee_id: UUID | None = None,
) -> list[ActionResponse]:
    return await list_actions(
        workspace_id,
        decision_id,
        current_user,
        service,
        action_status=action_status,
        assignee_id=assignee_id,
    )


@router.get(
    "/actions/{action_id}",
    response_model=ActionResponse,
    tags=["Implementation Actions"],
    summary="Get an implementation action",
)
async def get_action_route(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> ActionResponse:
    return await get_action(workspace_id, decision_id, action_id, current_user, service)


@router.patch(
    "/actions/{action_id}",
    response_model=ActionResponse,
    tags=["Implementation Actions"],
    summary="Update an implementation action",
)
async def update_action_route(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    payload: ActionUpdateRequest,
    current_user: CurrentUser,
    service: Service,
) -> ActionResponse:
    return await update_action(workspace_id, decision_id, action_id, payload, current_user, service)


@router.post(
    "/actions/{action_id}/transitions",
    response_model=ActionResponse,
    tags=["Implementation Actions"],
    summary="Transition an implementation action",
)
async def transition_action_route(
    workspace_id: UUID,
    decision_id: UUID,
    action_id: UUID,
    payload: ActionTransitionRequest,
    current_user: CurrentUser,
    service: Service,
) -> ActionResponse:
    return await transition_action(
        workspace_id, decision_id, action_id, payload, current_user, service
    )


@router.post(
    "/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Decision Reviews"],
    summary="Schedule a decision review",
)
async def create_review_route(
    workspace_id: UUID,
    decision_id: UUID,
    payload: ReviewCreateRequest,
    current_user: CurrentUser,
    service: Service,
) -> ReviewResponse:
    return await create_review(workspace_id, decision_id, payload, current_user, service)


@router.get(
    "/reviews",
    response_model=list[ReviewResponse],
    tags=["Decision Reviews"],
    summary="List decision reviews",
)
async def list_reviews_route(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> list[ReviewResponse]:
    return await list_reviews(workspace_id, decision_id, current_user, service)


@router.get(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
    tags=["Decision Reviews"],
    summary="Get a decision review",
)
async def get_review_route(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> ReviewResponse:
    return await get_review(workspace_id, decision_id, review_id, current_user, service)


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
    tags=["Decision Reviews"],
    summary="Reschedule a decision review",
)
async def update_review_route(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    payload: ReviewUpdateRequest,
    current_user: CurrentUser,
    service: Service,
) -> ReviewResponse:
    return await update_review(workspace_id, decision_id, review_id, payload, current_user, service)


@router.post(
    "/reviews/{review_id}/cancel",
    response_model=ReviewResponse,
    tags=["Decision Reviews"],
    summary="Cancel a scheduled decision review",
)
async def cancel_review_route(
    workspace_id: UUID,
    decision_id: UUID,
    review_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> ReviewResponse:
    return await cancel_review(workspace_id, decision_id, review_id, current_user, service)
