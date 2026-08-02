from collections.abc import Awaitable, Callable

from fastapi import HTTPException

from app.core.exceptions import DecisionNotFoundError, WorkspaceNotFoundError


async def execute_meeting_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    except DecisionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Decision not found") from error
