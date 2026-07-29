from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReviewStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReviewOutcome(StrEnum):
    CONFIRMED = "confirmed"
    REOPENED = "reopened"
    SUPERSEDED = "superseded"


action_status_type = Enum(
    ActionStatus,
    name="action_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)

review_status_type = Enum(
    ReviewStatus,
    name="review_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)

review_outcome_type = Enum(
    ReviewOutcome,
    name="review_outcome",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)


class ImplementationAction(Base):
    __tablename__ = "implementation_actions"
    __table_args__ = (
        CheckConstraint(
            (
                "(status = 'completed' AND completed_at IS NOT NULL) OR "
                "(status <> 'completed' AND completed_at IS NULL)"
            ),
            name="ck_implementation_actions_completed_state",
        ),
        CheckConstraint(
            (
                "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR "
                "(status <> 'cancelled' AND cancelled_at IS NULL)"
            ),
            name="ck_implementation_actions_cancelled_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assignee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ActionStatus] = mapped_column(
        action_status_type,
        nullable=False,
        default=ActionStatus.TODO,
        index=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class DecisionReview(Base):
    __tablename__ = "decision_reviews"
    __table_args__ = (
        CheckConstraint(
            (
                "(status = 'scheduled' AND cancelled_at IS NULL "
                "AND cancelled_by_id IS NULL AND completed_at IS NULL "
                "AND completed_by_id IS NULL AND outcome IS NULL) OR "
                "(status = 'cancelled' AND cancelled_at IS NOT NULL "
                "AND cancelled_by_id IS NOT NULL AND completed_at IS NULL "
                "AND completed_by_id IS NULL AND outcome IS NULL) OR "
                "(status = 'completed' AND cancelled_at IS NULL "
                "AND cancelled_by_id IS NULL AND completed_at IS NOT NULL "
                "AND completed_by_id IS NOT NULL AND outcome IS NOT NULL)"
            ),
            name="ck_decision_reviews_terminal_state",
        ),
        Index(
            "uq_decision_reviews_one_scheduled_per_decision",
            "decision_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scheduled_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        review_status_type,
        nullable=False,
        default=ReviewStatus.SCHEDULED,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[ReviewOutcome | None] = mapped_column(
        review_outcome_type,
        nullable=True,
        index=True,
    )
    outcome_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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


class DecisionRevision(Base):
    __tablename__ = "decision_revisions"
    __table_args__ = (
        UniqueConstraint(
            "root_decision_id",
            "revision_number",
            name="uq_decision_revisions_root_number",
        ),
        UniqueConstraint(
            "predecessor_decision_id",
            name="uq_decision_revisions_predecessor",
        ),
        UniqueConstraint(
            "successor_decision_id",
            name="uq_decision_revisions_successor",
        ),
        UniqueConstraint("review_id", name="uq_decision_revisions_review"),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_decision_revisions_positive_number",
        ),
        CheckConstraint(
            "outcome IN ('reopened', 'superseded')",
            name="ck_decision_revisions_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    root_decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    predecessor_decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    successor_decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_lock_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decision_locks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    review_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decision_reviews.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(nullable=False)
    outcome: Mapped[ReviewOutcome] = mapped_column(
        review_outcome_type,
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
