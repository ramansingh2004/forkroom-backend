from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.decision import DecisionCategory, DecisionStatus


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone")
    return value


class DecisionCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    category: DecisionCategory = DecisionCategory.OTHER
    due_at: datetime | None = None
    review_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if len(normalized) < 3:
            raise ValueError("Decision title must contain at least 3 characters")
        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("due_at", "review_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "DecisionCreateRequest":
        if self.due_at is not None and self.review_at is not None and self.review_at <= self.due_at:
            raise ValueError("Review date must be after the decision due date")
        return self


class DecisionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    category: DecisionCategory | None = None
    due_at: datetime | None = None
    review_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        if len(normalized) < 3:
            raise ValueError("Decision title must contain at least 3 characters")
        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("due_at", "review_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class DecisionTransitionRequest(BaseModel):
    status: DecisionStatus


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    title: str
    summary: str | None
    category: DecisionCategory
    status: DecisionStatus
    due_at: datetime | None
    review_at: datetime | None
    closed_at: datetime | None
    archived_at: datetime | None
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime
