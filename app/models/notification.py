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
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationKind(StrEnum):
    ACTION_DUE = "action_due"
    DECISION_REVIEW = "decision_review"
    DECISION_DEADLINE = "decision_deadline"
    VOTING_CLOSE = "voting_close"
    MENTION = "mention"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    RETRY_SCHEDULED = "retry_scheduled"
    DELIVERED = "delivered"
    FAILED = "failed"


notification_kind_type = Enum(
    NotificationKind,
    name="notification_kind",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

notification_status_type = Enum(
    NotificationStatus,
    name="notification_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notifications_idempotency_key"),
        CheckConstraint("attempt_count >= 0", name="ck_notifications_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="ck_notifications_max_attempts"),
        CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_notifications_attempt_limit",
        ),
        CheckConstraint(
            (
                "(status = 'delivered' AND delivered_at IS NOT NULL AND failed_at IS NULL) OR "
                "(status = 'failed' AND failed_at IS NOT NULL AND delivered_at IS NULL) OR "
                "(status IN ('pending', 'delivering', 'retry_scheduled') "
                "AND delivered_at IS NULL AND failed_at IS NULL)"
            ),
            name="ck_notifications_terminal_state",
        ),
        Index(
            "ix_notifications_delivery_ready",
            "status",
            "available_at",
        ),
        Index(
            "ix_notifications_recipient_created",
            "recipient_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    recipient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[NotificationKind] = mapped_column(
        notification_kind_type,
        nullable=False,
        index=True,
    )
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    action_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        notification_status_type,
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
