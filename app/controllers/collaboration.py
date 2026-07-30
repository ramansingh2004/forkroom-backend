from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    CollaborationAccessDeniedError,
    DecisionNotFoundError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)


async def execute_collaboration_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Decision not found") from error
    except ProposalNotFoundError as error:
        raise HTTPException(status_code=404, detail="Proposal not found") from error
    except CollaborationAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document",
        ) from error
