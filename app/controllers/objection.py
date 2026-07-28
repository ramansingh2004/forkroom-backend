from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionNotFoundError,
    ObjectionAccessDeniedError,
    ObjectionImmutableError,
    ObjectionInvalidTransitionError,
    ObjectionNotFoundError,
    ProposalImmutableError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)


def _raise_objection_error(error: Exception) -> None:
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
    if isinstance(error, ObjectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Objection not found",
        ) from error
    if isinstance(error, ObjectionAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this objection action",
        ) from error
    if isinstance(
        error,
        ObjectionImmutableError | ProposalImmutableError | DecisionImmutableError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The objection, proposal, or decision cannot be changed",
        ) from error
    if isinstance(error, ObjectionInvalidTransitionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested objection status transition is invalid",
        ) from error
    raise error


async def execute_objection_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_objection_error(error)
        raise
