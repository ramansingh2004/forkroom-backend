from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionNotFoundError,
    ProposalNotFoundError,
    VoteAlreadyCastError,
    VotingAccessDeniedError,
    VotingBlockedByObjectionsError,
    VotingClosedError,
    VotingConflictError,
    VotingInvalidTransitionError,
    VotingResultUnavailableError,
    VotingSessionNotFoundError,
    WorkspaceNotFoundError,
)


def _raise_voting_error(error: Exception) -> None:
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
    if isinstance(error, VotingSessionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voting session not found",
        ) from error
    if isinstance(error, ProposalNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal is not an option in this voting session",
        ) from error
    if isinstance(error, VotingAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this voting action",
        ) from error
    if isinstance(error, VotingBlockedByObjectionsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve every blocking objection before opening voting",
        ) from error
    if isinstance(error, VoteAlreadyCastError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already voted in this session",
        ) from error
    if isinstance(error, VotingResultUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Voting results are available only after the session closes",
        ) from error
    if isinstance(error, VotingClosedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The voting session is not accepting ballots",
        ) from error
    if isinstance(
        error,
        VotingConflictError | VotingInvalidTransitionError | DecisionImmutableError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested voting session state is invalid",
        ) from error
    raise error


async def execute_voting_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_voting_error(error)
        raise
