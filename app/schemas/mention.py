from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MentionStatus(StrEnum):
    ALL = "all"
    UNREAD = "unread"


class MentionActorResponse(BaseModel):
    id: UUID
    display_name: str
    avatar_url: str | None


class MentionContextResponse(BaseModel):
    type: Literal["decision_comment", "proposal_comment", "objection_comment"]
    decision_id: UUID
    decision_title: str
    proposal_id: UUID | None = None
    proposal_title: str | None = None
    objection_id: UUID | None = None
    objection_title: str | None = None


class MentionResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    comment_id: UUID
    mentioned_by: MentionActorResponse
    excerpt: str
    context: MentionContextResponse
    href: str
    created_at: datetime
    read_at: datetime | None


class MentionListResponse(BaseModel):
    items: list[MentionResponse]
    unread_count: int = Field(ge=0)
    next_cursor: str | None


class MentionReadResponse(BaseModel):
    id: UUID
    read_at: datetime | None


class MentionMarkAllReadResponse(BaseModel):
    updated: int = Field(ge=0)


class MentionUnreadCountResponse(BaseModel):
    count: int = Field(ge=0)
