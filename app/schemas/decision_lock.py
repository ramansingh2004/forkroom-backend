from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DecisionLockCreateRequest(BaseModel):
    voting_session_id: UUID


class DecisionLockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    voting_session_id: UUID
    winning_proposal_id: UUID
    locked_by_id: UUID
    snapshot_version: int
    snapshot: dict[str, object]
    document_hash: str
    locked_at: datetime


class DecisionLockVerificationResponse(BaseModel):
    decision_id: UUID
    document_hash: str
    computed_hash: str
    valid: bool
