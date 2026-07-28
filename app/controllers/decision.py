from uuid import UUID

from fastapi import HTTPException, status

from app.core.exceptions import (
    DecisionAccessDeniedError,
    DecisionImmutableError,
    DecisionInvalidTransitionError,
    DecisionNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.decision import DecisionCategory, DecisionStatus
from app.models.user import User
from app.schemas.decision import (
    DecisionCreateRequest,
    DecisionResponse,
    DecisionTransitionRequest,
    DecisionUpdateRequest,
)
from app.services.decision import DecisionService


def _raise_decision_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        ) from error
    if isinstance(error, DecisionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Decision not found",
        ) from error
    if isinstance(error, DecisionAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this decision action",
        ) from error
    if isinstance(error, DecisionInvalidTransitionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested decision state or schedule is invalid",
        ) from error
    if isinstance(error, DecisionImmutableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed or archived decisions cannot be changed",
        ) from error
    raise error


async def create_decision(
    workspace_id: UUID,
    payload: DecisionCreateRequest,
    current_user: User,
    service: DecisionService,
) -> DecisionResponse:
    try:
        decision = await service.create(current_user, workspace_id, payload)
    except Exception as error:
        _raise_decision_error(error)
        raise
    return DecisionResponse.model_validate(decision)


async def list_decisions(
    workspace_id: UUID,
    current_user: User,
    service: DecisionService,
    *,
    decision_status: DecisionStatus | None,
    category: DecisionCategory | None,
    limit: int,
    offset: int,
) -> list[DecisionResponse]:
    try:
        decisions = await service.list_decisions(
            current_user,
            workspace_id,
            status=decision_status,
            category=category,
            limit=limit,
            offset=offset,
        )
    except Exception as error:
        _raise_decision_error(error)
        raise
    return [DecisionResponse.model_validate(decision) for decision in decisions]


async def get_decision(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: User,
    service: DecisionService,
) -> DecisionResponse:
    try:
        decision = await service.get(current_user, workspace_id, decision_id)
    except Exception as error:
        _raise_decision_error(error)
        raise
    return DecisionResponse.model_validate(decision)


async def update_decision(
    workspace_id: UUID,
    decision_id: UUID,
    payload: DecisionUpdateRequest,
    current_user: User,
    service: DecisionService,
) -> DecisionResponse:
    try:
        decision = await service.update(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    except Exception as error:
        _raise_decision_error(error)
        raise
    return DecisionResponse.model_validate(decision)


async def transition_decision(
    workspace_id: UUID,
    decision_id: UUID,
    payload: DecisionTransitionRequest,
    current_user: User,
    service: DecisionService,
) -> DecisionResponse:
    try:
        decision = await service.transition(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    except Exception as error:
        _raise_decision_error(error)
        raise
    return DecisionResponse.model_validate(decision)


async def delete_decision(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: User,
    service: DecisionService,
) -> None:
    try:
        await service.delete(current_user, workspace_id, decision_id)
    except Exception as error:
        _raise_decision_error(error)
