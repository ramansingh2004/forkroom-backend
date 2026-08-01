from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.attachment import AttachmentStatus


class AttachmentCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    decision_id: UUID | None = None
    proposal_id: UUID | None = None

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/").rsplit("/", 1)[-1]
        if normalized in {"", ".", ".."}:
            raise ValueError("filename must contain a valid base name")
        return normalized


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    decision_id: UUID | None
    proposal_id: UUID | None
    uploaded_by_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str | None
    status: AttachmentStatus
    processing_attempts: int
    processing_error: str | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AttachmentUploadResponse(BaseModel):
    attachment: AttachmentResponse
    upload_url: str
    expires_at: datetime


class AttachmentDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime
