from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationKind, NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    kind: NotificationKind
    source_id: UUID
    actor_id: UUID | None
    entity_type: str | None
    entity_id: UUID | None
    action_url: str | None
    title: str
    body: str
    status: NotificationStatus
    attempt_count: int
    read_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread: int = Field(ge=0)


class MarkAllReadResponse(BaseModel):
    updated: int = Field(ge=0)
