from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentInvalidStateError,
    AttachmentInvalidTargetError,
    AttachmentNotFoundError,
    AttachmentTooLargeError,
    WorkspaceNotFoundError,
)


def _raise_attachment_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError | AttachmentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace or attachment not found",
        ) from error
    if isinstance(error, AttachmentAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this attachment action",
        ) from error
    if isinstance(error, AttachmentTooLargeError):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Attachment exceeds the configured size limit",
        ) from error
    if isinstance(error, AttachmentInvalidTargetError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Attachment target is invalid or outside this workspace",
        ) from error
    if isinstance(error, AttachmentInvalidStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment is not in the required lifecycle state",
        ) from error
    raise error


async def execute_attachment_action[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as error:
        _raise_attachment_error(error)
        raise
