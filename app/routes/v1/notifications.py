from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.controllers.notification import (
    get_notification,
    list_notifications,
    mark_all_read,
    mark_notification_read,
    unread_count,
)
from app.dependencies.auth import get_current_user
from app.dependencies.notification import get_notification_service
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("", response_model=NotificationListResponse, summary="List my notifications")
async def list_notifications_route(
    current_user: CurrentUser,
    service: Service,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationListResponse:
    return await list_notifications(
        current_user,
        service,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get my unread notification count",
)
async def unread_count_route(
    current_user: CurrentUser,
    service: Service,
) -> UnreadCountResponse:
    return await unread_count(current_user, service)


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    summary="Mark all my notifications as read",
)
async def mark_all_read_route(
    current_user: CurrentUser,
    service: Service,
) -> MarkAllReadResponse:
    return await mark_all_read(current_user, service)


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get one of my notifications",
)
async def get_notification_route(
    notification_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> NotificationResponse:
    return await get_notification(notification_id, current_user, service)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark one of my notifications as read",
)
async def mark_notification_read_route(
    notification_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> NotificationResponse:
    return await mark_notification_read(notification_id, current_user, service)
