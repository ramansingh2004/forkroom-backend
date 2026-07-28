from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.workspace import WorkspaceRole


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


class AssignableWorkspaceRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if len(normalized) < 2:
            raise ValueError("Workspace name must contain at least 2 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        return normalized or None


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        if len(normalized) < 2:
            raise ValueError("Workspace name must contain at least 2 characters")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        return normalized or None


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    created_at: datetime
    updated_at: datetime


class WorkspaceMemberCreateRequest(BaseModel):
    email: EmailStr
    role: AssignableWorkspaceRole = AssignableWorkspaceRole.MEMBER


class WorkspaceMemberUpdateRequest(BaseModel):
    role: AssignableWorkspaceRole


class WorkspaceMemberResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    display_name: str
    avatar_url: str | None
    role: WorkspaceRole
    joined_at: datetime
