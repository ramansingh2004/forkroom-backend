from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionLockAccessDeniedError,
    DecisionLockConflictError,
    DecisionLockInvalidResultError,
    DecisionLockNotFoundError,
    DecisionNotFoundError,
    ProposalNotFoundError,
    VotingBlockedByObjectionsError,
    VotingResultUnavailableError,
    VotingSessionNotFoundError,
    WorkspaceNotFoundError,
)


def _raise_decision_lock_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, DecisionNotFoundError):
        raise HTTPException(status_code=404, detail="Decision not found") from error
    if isinstance(error, DecisionLockNotFoundError):
        raise HTTPException(status_code=404, detail="Decision lock not found") from error
    if isinstance(error, VotingSessionNotFoundError):
        raise HTTPException(status_code=404, detail="Voting session not found") from error
    if isinstance(error, ProposalNotFoundError):
        raise HTTPException(status_code=404, detail="Winning proposal not found") from error
    if isinstance(error, DecisionLockAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and admins can lock decisions",
        ) from error
    if isinstance(error, VotingBlockedByObjectionsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve every blocking objection before locking the decision",
        ) from error
    if isinstance(error, VotingResultUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Close the voting session before locking the decision",
        ) from error
    if isinstance(
        error,
        DecisionImmutableError | DecisionLockConflictError | DecisionLockInvalidResultError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The decision cannot be locked from this voting result",
        ) from error
    raise error


async def execute_decision_lock_action[T](
    action: Callable[[], Awaitable[T]],
) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_decision_lock_error(error)
        raise
