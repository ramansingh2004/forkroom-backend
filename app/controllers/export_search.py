from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    DecisionExportAccessDeniedError,
    DecisionExportInvalidStateError,
    DecisionExportNotFoundError,
    DecisionLockNotFoundError,
    SearchAccessDeniedError,
    WorkspaceNotFoundError,
)


def _raise_export_search_error(error: Exception) -> None:
    if isinstance(
        error,
        WorkspaceNotFoundError | DecisionLockNotFoundError | DecisionExportNotFoundError,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        ) from error
    if isinstance(error, DecisionExportAccessDeniedError | SearchAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this operation",
        ) from error
    if isinstance(error, DecisionExportInvalidStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The decision export is not available or its source is invalid",
        ) from error
    raise error


async def execute_export_search_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_export_search_error(error)
        raise
