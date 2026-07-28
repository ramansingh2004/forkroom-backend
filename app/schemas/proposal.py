from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.proposal import ProposalStatus


def _normalize_required(value: str) -> str:
    return " ".join(value.split())


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ProposalCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    content: str | None = Field(default=None, max_length=50_000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = _normalize_required(value)
        if len(normalized) < 3:
            raise ValueError("Proposal title must contain at least 3 characters")
        return normalized

    @field_validator("summary", "content")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional(value)


class ProposalUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    content: str | None = Field(default=None, max_length=50_000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_required(value)
        if len(normalized) < 3:
            raise ValueError("Proposal title must contain at least 3 characters")
        return normalized

    @field_validator("summary", "content")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional(value)


class ProposalTransitionRequest(BaseModel):
    status: ProposalStatus


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    created_by_id: UUID
    title: str
    summary: str | None
    content: str | None
    status: ProposalStatus
    submitted_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CriterionCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    weight: int = Field(default=1, ge=1, le=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = _normalize_required(value)
        if len(normalized) < 2:
            raise ValueError("Criterion name must contain at least 2 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional(value)


class CriterionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    weight: int | None = Field(default=None, ge=1, le=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_required(value)
        if len(normalized) < 2:
            raise ValueError("Criterion name must contain at least 2 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional(value)


class CriterionReorderRequest(BaseModel):
    criterion_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("criterion_ids")
    @classmethod
    def require_unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Criterion IDs must be unique")
        return value


class CriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    created_by_id: UUID
    name: str
    description: str | None
    weight: int
    position: int
    created_at: datetime
    updated_at: datetime


class ProposalScoreUpsertRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str | None = Field(default=None, max_length=1000)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str | None) -> str | None:
        return _normalize_optional(value)


class ProposalScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_id: UUID
    criterion_id: UUID
    scored_by_id: UUID
    score: int
    rationale: str | None
    created_at: datetime
    updated_at: datetime


class ProposalComparisonResponse(BaseModel):
    proposal: ProposalResponse
    scores: list[ProposalScoreResponse]
    weighted_score: float | None
