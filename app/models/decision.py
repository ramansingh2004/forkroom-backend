from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DecisionCategory(StrEnum):
    TECHNOLOGY = "technology"
    ARCHITECTURE = "architecture"
    DELIVERY = "delivery"
    TEAM_PROCESS = "team_process"
    OTHER = "other"


class DecisionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    LOCKED = "locked"
    ARCHIVED = "archived"


decision_category_type = Enum(
    DecisionCategory,
    name="decision_category",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

decision_status_type = Enum(
    DecisionStatus,
    name="decision_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            (
                "(status = 'locked' AND locked_at IS NOT NULL) OR "
                "(status <> 'locked' AND locked_at IS NULL)"
            ),
            name="ck_decisions_locked_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[DecisionCategory] = mapped_column(
        decision_category_type,
        nullable=False,
        default=DecisionCategory.OTHER,
    )
    status: Mapped[DecisionStatus] = mapped_column(
        decision_status_type,
        nullable=False,
        default=DecisionStatus.DRAFT,
        index=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class DecisionLock(Base):
    __tablename__ = "decision_locks"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_decision_locks_decision_id"),
        UniqueConstraint("voting_session_id", name="uq_decision_locks_voting_session_id"),
        CheckConstraint("snapshot_version >= 1", name="ck_decision_locks_snapshot_version"),
        CheckConstraint(
            "length(document_hash) = 64",
            name="ck_decision_locks_document_hash_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    voting_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("voting_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    winning_proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    locked_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
