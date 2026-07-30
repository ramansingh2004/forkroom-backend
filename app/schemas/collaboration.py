from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class CollaborationPermission(StrEnum):
    READ = "read"
    WRITE = "write"


class CollaborationTokenResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int
    expires_at: datetime
    collaboration_url: str
    document_id: UUID
    document_name: str
    permission: CollaborationPermission
