from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.controllers.decision_lock import execute_decision_lock_action
from app.dependencies.auth import get_current_user
from app.dependencies.decision_lock import get_decision_lock_service
from app.models.user import User
from app.schemas.decision_lock import (
    DecisionLockCreateRequest,
    DecisionLockResponse,
    DecisionLockVerificationResponse,
)
from app.services.decision_lock import DecisionLockService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions/{decision_id}/lock",
    tags=["Decision locking"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
DecisionLockServiceDependency = Annotated[
    DecisionLockService,
    Depends(get_decision_lock_service),
]


@router.post(
    "",
    response_model=DecisionLockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Lock an approved decision",
)
async def create_decision_lock(
    workspace_id: UUID,
    decision_id: UUID,
    payload: DecisionLockCreateRequest,
    current_user: CurrentUser,
    service: DecisionLockServiceDependency,
) -> DecisionLockResponse:
    decision_lock = await execute_decision_lock_action(
        lambda: service.create(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    )
    return DecisionLockResponse.model_validate(decision_lock)


@router.get(
    "",
    response_model=DecisionLockResponse,
    summary="Get the immutable decision record",
)
async def get_decision_lock(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionLockServiceDependency,
) -> DecisionLockResponse:
    decision_lock = await execute_decision_lock_action(
        lambda: service.get(current_user, workspace_id, decision_id)
    )
    return DecisionLockResponse.model_validate(decision_lock)


@router.get(
    "/verify",
    response_model=DecisionLockVerificationResponse,
    summary="Verify the decision snapshot hash",
)
async def verify_decision_lock(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionLockServiceDependency,
) -> DecisionLockVerificationResponse:
    return await execute_decision_lock_action(
        lambda: service.verify(current_user, workspace_id, decision_id)
    )
