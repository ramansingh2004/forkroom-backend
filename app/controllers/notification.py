from uuid import UUID

from fastapi import HTTPException

from app.core.exceptions import NotificationNotFoundError
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification import NotificationService


def _raise_notification_error(error: Exception) -> None:
    if isinstance(error, NotificationNotFoundError):
        raise HTTPException(status_code=404, detail="Notification not found") from error
    raise error


async def list_notifications(
    current_user: User,
    service: NotificationService,
    *,
    unread_only: bool,
    limit: int,
    offset: int,
) -> NotificationListResponse:
    items, total, unread = await service.list_notifications(
        current_user,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=total,
        unread=unread,
        limit=limit,
        offset=offset,
    )


async def get_notification(
    notification_id: UUID,
    current_user: User,
    service: NotificationService,
) -> NotificationResponse:
    try:
        notification = await service.get_notification(current_user, notification_id)
    except Exception as error:
        _raise_notification_error(error)
        raise
    return NotificationResponse.model_validate(notification)


async def mark_notification_read(
    notification_id: UUID,
    current_user: User,
    service: NotificationService,
) -> NotificationResponse:
    try:
        notification = await service.mark_read(current_user, notification_id)
    except Exception as error:
        _raise_notification_error(error)
        raise
    return NotificationResponse.model_validate(notification)


async def mark_all_read(
    current_user: User,
    service: NotificationService,
) -> MarkAllReadResponse:
    return MarkAllReadResponse(updated=await service.mark_all_read(current_user))


async def unread_count(
    current_user: User,
    service: NotificationService,
) -> UnreadCountResponse:
    return UnreadCountResponse(unread=await service.unread_count(current_user))
