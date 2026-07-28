from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.proposal import execute_proposal_action
from app.dependencies.auth import get_current_user
from app.dependencies.proposal import get_proposal_service
from app.models.proposal import ProposalStatus
from app.models.user import User
from app.schemas.proposal import (
    CriterionCreateRequest,
    CriterionReorderRequest,
    CriterionResponse,
    CriterionUpdateRequest,
    ProposalComparisonResponse,
    ProposalCreateRequest,
    ProposalResponse,
    ProposalScoreResponse,
    ProposalScoreUpsertRequest,
    ProposalTransitionRequest,
    ProposalUpdateRequest,
)
from app.services.proposal import ProposalService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions/{decision_id}",
    tags=["Proposals and criteria"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
ProposalServiceDependency = Annotated[
    ProposalService,
    Depends(get_proposal_service),
]


@router.get(
    "/comparison",
    response_model=list[ProposalComparisonResponse],
    summary="Compare submitted proposals using weighted criteria",
)
async def compare_proposals(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> list[ProposalComparisonResponse]:
    return await execute_proposal_action(
        lambda: service.compare(current_user, workspace_id, decision_id)
    )


@router.post(
    "/proposals",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a proposal branch",
)
async def create_proposal(
    workspace_id: UUID,
    decision_id: UUID,
    payload: ProposalCreateRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ProposalResponse:
    proposal = await execute_proposal_action(
        lambda: service.create(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    )
    return ProposalResponse.model_validate(proposal)


@router.get(
    "/proposals",
    response_model=list[ProposalResponse],
    summary="List proposal branches",
)
async def list_proposals(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
    proposal_status: Annotated[
        ProposalStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[ProposalResponse]:
    proposals = await execute_proposal_action(
        lambda: service.list_proposals(
            current_user,
            workspace_id,
            decision_id,
            status=proposal_status,
        )
    )
    return [ProposalResponse.model_validate(proposal) for proposal in proposals]


@router.get(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    summary="Get a proposal branch",
)
async def get_proposal(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ProposalResponse:
    proposal = await execute_proposal_action(
        lambda: service.get(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
        )
    )
    return ProposalResponse.model_validate(proposal)


@router.patch(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    summary="Update a draft proposal branch",
)
async def update_proposal(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    payload: ProposalUpdateRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ProposalResponse:
    proposal = await execute_proposal_action(
        lambda: service.update(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            payload,
        )
    )
    return ProposalResponse.model_validate(proposal)


@router.post(
    "/proposals/{proposal_id}/transitions",
    response_model=ProposalResponse,
    summary="Submit, reopen, or withdraw a proposal",
)
async def transition_proposal(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ProposalResponse:
    proposal = await execute_proposal_action(
        lambda: service.transition(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            payload,
        )
    )
    return ProposalResponse.model_validate(proposal)


@router.delete(
    "/proposals/{proposal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft proposal branch",
)
async def delete_proposal(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> None:
    await execute_proposal_action(
        lambda: service.delete(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
        )
    )


@router.put(
    "/proposals/{proposal_id}/scores/{criterion_id}",
    response_model=ProposalScoreResponse,
    summary="Score a submitted proposal against a criterion",
)
async def upsert_proposal_score(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    criterion_id: UUID,
    payload: ProposalScoreUpsertRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ProposalScoreResponse:
    proposal_score = await execute_proposal_action(
        lambda: service.upsert_score(
            current_user,
            workspace_id,
            decision_id,
            proposal_id,
            criterion_id,
            payload,
        )
    )
    return ProposalScoreResponse.model_validate(proposal_score)


@router.post(
    "/criteria",
    response_model=CriterionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a weighted comparison criterion",
)
async def create_criterion(
    workspace_id: UUID,
    decision_id: UUID,
    payload: CriterionCreateRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> CriterionResponse:
    criterion = await execute_proposal_action(
        lambda: service.create_criterion(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    )
    return CriterionResponse.model_validate(criterion)


@router.get(
    "/criteria",
    response_model=list[CriterionResponse],
    summary="List ordered comparison criteria",
)
async def list_criteria(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> list[CriterionResponse]:
    criteria = await execute_proposal_action(
        lambda: service.list_criteria(
            current_user,
            workspace_id,
            decision_id,
        )
    )
    return [CriterionResponse.model_validate(criterion) for criterion in criteria]


@router.put(
    "/criteria/order",
    response_model=list[CriterionResponse],
    summary="Replace the comparison criterion order",
)
async def reorder_criteria(
    workspace_id: UUID,
    decision_id: UUID,
    payload: CriterionReorderRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> list[CriterionResponse]:
    criteria = await execute_proposal_action(
        lambda: service.reorder_criteria(
            current_user,
            workspace_id,
            decision_id,
            payload,
        )
    )
    return [CriterionResponse.model_validate(criterion) for criterion in criteria]


@router.patch(
    "/criteria/{criterion_id}",
    response_model=CriterionResponse,
    summary="Update a comparison criterion",
)
async def update_criterion(
    workspace_id: UUID,
    decision_id: UUID,
    criterion_id: UUID,
    payload: CriterionUpdateRequest,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> CriterionResponse:
    criterion = await execute_proposal_action(
        lambda: service.update_criterion(
            current_user,
            workspace_id,
            decision_id,
            criterion_id,
            payload,
        )
    )
    return CriterionResponse.model_validate(criterion)


@router.delete(
    "/criteria/{criterion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comparison criterion",
)
async def delete_criterion(
    workspace_id: UUID,
    decision_id: UUID,
    criterion_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> None:
    await execute_proposal_action(
        lambda: service.delete_criterion(
            current_user,
            workspace_id,
            decision_id,
            criterion_id,
        )
    )
