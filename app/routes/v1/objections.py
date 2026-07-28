from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.objection import execute_objection_action
from app.dependencies.auth import get_current_user
from app.dependencies.objection import get_objection_service
from app.models.objection import ObjectionSeverity, ObjectionStatus
from app.models.user import User
from app.schemas.objection import (
    ObjectionCreateRequest,
    ObjectionResponse,
    ObjectionStatusEventResponse,
    ObjectionTransitionRequest,
    ObjectionUpdateRequest,
)
from app.services.objection import ObjectionService

router = APIRouter(
    prefix=(
        "/workspaces/{workspace_id}/decisions/{decision_id}/proposals/{proposal_id}/objections"
    ),
    tags=["Objections"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
ObjectionServiceDependency = Annotated[
    ObjectionService,
    Depends(get_objection_service),
]


@router.post(
    "",
    response_model=ObjectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Raise a structured objection",
)
async def create_objection(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    payload: ObjectionCreateRequest,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
) -> ObjectionResponse:
    objection = await execute_objection_action(
        lambda: service.create(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            payload,
        )
    )
    return ObjectionResponse.model_validate(objection)


@router.get(
    "",
    response_model=list[ObjectionResponse],
    summary="List structured objections",
)
async def list_objections(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
    severity: ObjectionSeverity | None = None,
    objection_status: Annotated[
        ObjectionStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[ObjectionResponse]:
    objections = await execute_objection_action(
        lambda: service.list_objections(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            severity=severity,
            status=objection_status,
        )
    )
    return [ObjectionResponse.model_validate(objection) for objection in objections]


@router.get(
    "/{objection_id}",
    response_model=ObjectionResponse,
    summary="Get a structured objection",
)
async def get_objection(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    objection_id: UUID,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
) -> ObjectionResponse:
    objection = await execute_objection_action(
        lambda: service.get(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            objection_id,
        )
    )
    return ObjectionResponse.model_validate(objection)


@router.patch(
    "/{objection_id}",
    response_model=ObjectionResponse,
    summary="Update an open objection",
)
async def update_objection(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    objection_id: UUID,
    payload: ObjectionUpdateRequest,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
) -> ObjectionResponse:
    objection = await execute_objection_action(
        lambda: service.update(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            objection_id,
            payload,
        )
    )
    return ObjectionResponse.model_validate(objection)


@router.post(
    "/{objection_id}/transitions",
    response_model=ObjectionResponse,
    summary="Resolve, dismiss, or reopen an objection",
)
async def transition_objection(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    objection_id: UUID,
    payload: ObjectionTransitionRequest,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
) -> ObjectionResponse:
    objection = await execute_objection_action(
        lambda: service.transition(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            objection_id,
            payload,
        )
    )
    return ObjectionResponse.model_validate(objection)


@router.get(
    "/{objection_id}/history",
    response_model=list[ObjectionStatusEventResponse],
    summary="List objection resolution history",
)
async def list_objection_history(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    objection_id: UUID,
    current_user: CurrentUser,
    service: ObjectionServiceDependency,
) -> list[ObjectionStatusEventResponse]:
    events = await execute_objection_action(
        lambda: service.list_history(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            objection_id,
        )
    )
    return [ObjectionStatusEventResponse.model_validate(event) for event in events]
