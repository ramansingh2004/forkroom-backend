from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.voting import VotingSessionStatus


class VotingSessionCreateRequest(BaseModel):
    quorum_percentage: int = Field(default=60, ge=1, le=100)
    closes_at: datetime | None = None

    @model_validator(mode="after")
    def validate_closing_time(self) -> "VotingSessionCreateRequest":
        if self.closes_at is not None:
            if self.closes_at.utcoffset() is None:
                raise ValueError("Voting close time must include a timezone")
            if self.closes_at <= datetime.now(UTC):
                raise ValueError("Voting close time must be in the future")
        return self


class VoteCastRequest(BaseModel):
    proposal_id: UUID


class VotingSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    created_by_id: UUID
    status: VotingSessionStatus
    quorum_percentage: int
    eligible_voter_count: int
    opened_at: datetime | None
    closes_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    voting_session_id: UUID
    voter_id: UUID
    proposal_id: UUID
    created_at: datetime


class ProposalVoteTallyResponse(BaseModel):
    proposal_id: UUID
    votes: int
    percentage: float


class VotingResultResponse(BaseModel):
    voting_session_id: UUID
    eligible_voter_count: int
    votes_cast: int
    quorum_percentage: int
    required_votes: int
    quorum_met: bool
    result_valid: bool
    winner_proposal_id: UUID | None
    is_tie: bool
    tallies: list[ProposalVoteTallyResponse]
