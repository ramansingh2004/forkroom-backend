from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.objection import ObjectionSeverity, ObjectionStatus


def _normalize_required(value: str) -> str:
    return " ".join(value.split())


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ObjectionCreateRequest(BaseModel):
    severity: ObjectionSeverity
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=10_000)

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = _normalize_required(value)
        if len(normalized) < 3:
            raise ValueError("Objection text must contain at least 3 characters")
        return normalized


class ObjectionUpdateRequest(BaseModel):
    severity: ObjectionSeverity | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=10_000)

    @field_validator("title", "description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_required(value)
        if len(normalized) < 3:
            raise ValueError("Objection text must contain at least 3 characters")
        return normalized


class ObjectionTransitionRequest(BaseModel):
    status: ObjectionStatus
    note: str = Field(min_length=3, max_length=5000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = _normalize_optional(value)
        if normalized is None or len(normalized) < 3:
            raise ValueError("A transition note with at least 3 characters is required")
        return normalized


class ObjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_id: UUID
    created_by_id: UUID
    severity: ObjectionSeverity
    status: ObjectionStatus
    title: str
    description: str
    resolution_note: str | None
    resolved_by_id: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ObjectionStatusEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    objection_id: UUID
    actor_id: UUID
    from_status: ObjectionStatus
    to_status: ObjectionStatus
    note: str
    created_at: datetime
