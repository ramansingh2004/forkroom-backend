from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.decision import (
    create_decision,
    delete_decision,
    get_decision,
    list_decisions,
    transition_decision,
    update_decision,
)
from app.dependencies.auth import get_current_user
from app.dependencies.decision import get_decision_service
from app.models.decision import DecisionCategory, DecisionStatus
from app.models.user import User
from app.schemas.decision import (
    DecisionCreateRequest,
    DecisionResponse,
    DecisionTransitionRequest,
    DecisionUpdateRequest,
)
from app.services.decision import DecisionService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions",
    tags=["Decisions"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
DecisionServiceDependency = Annotated[
    DecisionService,
    Depends(get_decision_service),
]


@router.post(
    "",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft decision",
)
async def create(
    workspace_id: UUID,
    payload: DecisionCreateRequest,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
) -> DecisionResponse:
    return await create_decision(
        workspace_id,
        payload,
        current_user,
        service,
    )


@router.get(
    "",
    response_model=list[DecisionResponse],
    summary="List decisions in a workspace",
)
async def list_all(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
    decision_status: Annotated[
        DecisionStatus | None,
        Query(alias="status"),
    ] = None,
    category: DecisionCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DecisionResponse]:
    return await list_decisions(
        workspace_id,
        current_user,
        service,
        decision_status=decision_status,
        category=category,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{decision_id}",
    response_model=DecisionResponse,
    summary="Get a decision",
)
async def get_one(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
) -> DecisionResponse:
    return await get_decision(
        workspace_id,
        decision_id,
        current_user,
        service,
    )


@router.patch(
    "/{decision_id}",
    response_model=DecisionResponse,
    summary="Update an editable decision",
)
async def update(
    workspace_id: UUID,
    decision_id: UUID,
    payload: DecisionUpdateRequest,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
) -> DecisionResponse:
    return await update_decision(
        workspace_id,
        decision_id,
        payload,
        current_user,
        service,
    )


@router.post(
    "/{decision_id}/transitions",
    response_model=DecisionResponse,
    summary="Transition a decision to another lifecycle state",
)
async def transition(
    workspace_id: UUID,
    decision_id: UUID,
    payload: DecisionTransitionRequest,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
) -> DecisionResponse:
    return await transition_decision(
        workspace_id,
        decision_id,
        payload,
        current_user,
        service,
    )


@router.delete(
    "/{decision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft decision",
)
async def delete(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionServiceDependency,
) -> None:
    await delete_decision(
        workspace_id,
        decision_id,
        current_user,
        service,
    )
