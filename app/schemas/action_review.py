from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.action_review import ActionStatus, ReviewStatus


def _normalize_required_text(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) < 3:
        raise ValueError("Value must contain at least 3 characters")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone")
    return value


class ActionCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: UUID
    due_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("due_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class ActionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: UUID | None = None
    due_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("due_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class ActionTransitionRequest(BaseModel):
    status: ActionStatus


class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    created_by_id: UUID
    assignee_id: UUID
    title: str
    description: str | None
    status: ActionStatus
    due_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewCreateRequest(BaseModel):
    scheduled_for: datetime
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("scheduled_for")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        checked = _require_timezone(value)
        assert checked is not None
        return checked

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ReviewUpdateRequest(BaseModel):
    scheduled_for: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("scheduled_for")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    scheduled_by_id: UUID
    scheduled_for: datetime
    status: ReviewStatus
    notes: str | None
    cancelled_by_id: UUID | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
