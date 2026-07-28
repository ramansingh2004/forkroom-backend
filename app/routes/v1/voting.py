from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.controllers.voting import execute_voting_action
from app.dependencies.auth import get_current_user
from app.dependencies.voting import get_voting_service
from app.models.user import User
from app.schemas.voting import (
    VoteCastRequest,
    VoteResponse,
    VotingResultResponse,
    VotingSessionCreateRequest,
    VotingSessionResponse,
)
from app.services.voting import VotingService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions/{decision_id}/voting-sessions",
    tags=["Voting"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
VotingServiceDependency = Annotated[
    VotingService,
    Depends(get_voting_service),
]


@router.post(
    "",
    response_model=VotingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft voting session",
)
async def create_voting_session(
    workspace_id: UUID,
    decision_id: UUID,
    payload: VotingSessionCreateRequest,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingSessionResponse:
    voting_session = await execute_voting_action(
        lambda: service.create_session(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    )
    return VotingSessionResponse.model_validate(voting_session)


@router.get(
    "",
    response_model=list[VotingSessionResponse],
    summary="List voting sessions",
)
async def list_voting_sessions(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> list[VotingSessionResponse]:
    voting_sessions = await execute_voting_action(
        lambda: service.list_sessions(
            current_user,
            workspace_id,
            decision_id,
        )
    )
    return [
        VotingSessionResponse.model_validate(voting_session) for voting_session in voting_sessions
    ]


@router.get(
    "/{voting_session_id}",
    response_model=VotingSessionResponse,
    summary="Get a voting session",
)
async def get_voting_session(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingSessionResponse:
    voting_session = await execute_voting_action(
        lambda: service.get_session(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
        )
    )
    return VotingSessionResponse.model_validate(voting_session)


@router.post(
    "/{voting_session_id}/open",
    response_model=VotingSessionResponse,
    summary="Open a voting session",
)
async def open_voting_session(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingSessionResponse:
    voting_session = await execute_voting_action(
        lambda: service.open_session(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
        )
    )
    return VotingSessionResponse.model_validate(voting_session)


@router.post(
    "/{voting_session_id}/votes",
    response_model=VoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cast one ballot",
)
async def cast_vote(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    payload: VoteCastRequest,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VoteResponse:
    vote = await execute_voting_action(
        lambda: service.cast_vote(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
            payload,
        )
    )
    return VoteResponse.model_validate(vote)


@router.post(
    "/{voting_session_id}/close",
    response_model=VotingSessionResponse,
    summary="Close a voting session",
)
async def close_voting_session(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingSessionResponse:
    voting_session = await execute_voting_action(
        lambda: service.close_session(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
        )
    )
    return VotingSessionResponse.model_validate(voting_session)


@router.post(
    "/{voting_session_id}/cancel",
    response_model=VotingSessionResponse,
    summary="Cancel a voting session",
)
async def cancel_voting_session(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingSessionResponse:
    voting_session = await execute_voting_action(
        lambda: service.cancel_session(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
        )
    )
    return VotingSessionResponse.model_validate(voting_session)


@router.get(
    "/{voting_session_id}/result",
    response_model=VotingResultResponse,
    summary="Get the closed voting result",
)
async def get_voting_result(
    workspace_id: UUID,
    decision_id: UUID,
    voting_session_id: UUID,
    current_user: CurrentUser,
    service: VotingServiceDependency,
) -> VotingResultResponse:
    return await execute_voting_action(
        lambda: service.get_result(
            current_user,
            workspace_id,
            decision_id,
            voting_session_id,
        )
    )
