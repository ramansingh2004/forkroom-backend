from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    CriterionAccessDeniedError,
    CriterionConflictError,
    CriterionNotFoundError,
    DecisionImmutableError,
    DecisionNotFoundError,
    ProposalAccessDeniedError,
    ProposalImmutableError,
    ProposalInvalidTransitionError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)


def _raise_proposal_error(error: Exception) -> None:
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
    if isinstance(error, ProposalNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        ) from error
    if isinstance(error, CriterionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparison criterion not found",
        ) from error
    if isinstance(
        error,
        ProposalAccessDeniedError | CriterionAccessDeniedError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this proposal action",
        ) from error
    if isinstance(
        error,
        ProposalImmutableError | DecisionImmutableError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The proposal or its parent decision cannot be changed",
        ) from error
    if isinstance(
        error,
        ProposalInvalidTransitionError | CriterionConflictError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested proposal state or criterion order is invalid",
        ) from error
    raise error


async def execute_proposal_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_proposal_error(error)
        raise
