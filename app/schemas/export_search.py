from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.export_search import ExportStatus


class DecisionExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    decision_id: UUID
    document_hash: str
    filename: str
    status: ExportStatus
    attempt_count: int
    size_bytes: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class DecisionExportDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime


class SearchResultResponse(BaseModel):
    decision_id: UUID
    title: str
    status: str
    category: str
    headline: str
    rank: float
    indexed_at: datetime


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
