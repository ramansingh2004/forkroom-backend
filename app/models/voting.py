from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VotingSessionStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


voting_session_status_type = Enum(
    VotingSessionStatus,
    name="voting_session_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)


class VotingSession(Base):
    __tablename__ = "voting_sessions"
    __table_args__ = (
        CheckConstraint(
            "quorum_percentage >= 1 AND quorum_percentage <= 100",
            name="ck_voting_sessions_quorum_percentage",
        ),
        CheckConstraint(
            "eligible_voter_count >= 0",
            name="ck_voting_sessions_eligible_voter_count",
        ),
        CheckConstraint(
            (
                "(status = 'draft' AND opened_at IS NULL AND closed_at IS NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'open' AND opened_at IS NOT NULL AND closed_at IS NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'closed' AND opened_at IS NOT NULL AND closed_at IS NOT NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'cancelled' AND closed_at IS NULL AND cancelled_at IS NOT NULL)"
            ),
            name="ck_voting_sessions_status_timestamps",
        ),
        Index(
            "uq_voting_sessions_one_unfinished_per_decision",
            "decision_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'open')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[VotingSessionStatus] = mapped_column(
        voting_session_status_type,
        nullable=False,
        default=VotingSessionStatus.DRAFT,
        index=True,
    )
    quorum_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_voter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class VotingEligibleVoter(Base):
    __tablename__ = "voting_eligible_voters"
    __table_args__ = (
        UniqueConstraint(
            "voting_session_id",
            "user_id",
            name="uq_voting_eligible_voters_session_user",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    voting_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("voting_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class VotingSessionProposal(Base):
    __tablename__ = "voting_session_proposals"
    __table_args__ = (
        UniqueConstraint(
            "voting_session_id",
            "proposal_id",
            name="uq_voting_session_proposals_session_proposal",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    voting_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("voting_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint(
            "voting_session_id",
            "voter_id",
            name="uq_votes_session_voter",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    voting_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("voting_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voter_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
