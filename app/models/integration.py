from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntegrationProvider(StrEnum):
    SLACK = "slack"


class IntegrationConnectionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"


class IntegrationEventType(StrEnum):
    DECISION_ACTIVATED = "decision_activated"
    VOTING_OPENED = "voting_opened"
    VOTING_CLOSED = "voting_closed"
    DECISION_LOCKED = "decision_locked"
    ACTION_ASSIGNED = "action_assigned"
    REVIEW_DUE = "review_due"
    EXPORT_FAILED = "export_failed"


class IntegrationDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    RETRY_SCHEDULED = "retry_scheduled"
    DELIVERED = "delivered"
    FAILED = "failed"


class IntegrationWebhookStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class IntegrationOutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


integration_provider_type = Enum(
    IntegrationProvider,
    name="integration_provider",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

integration_connection_status_type = Enum(
    IntegrationConnectionStatus,
    name="integration_connection_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

integration_event_type = Enum(
    IntegrationEventType,
    name="integration_event_type",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=40,
)

integration_delivery_status_type = Enum(
    IntegrationDeliveryStatus,
    name="integration_delivery_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

integration_webhook_status_type = Enum(
    IntegrationWebhookStatus,
    name="integration_webhook_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)

integration_outbox_status_type = Enum(
    IntegrationOutboxStatus,
    name="integration_outbox_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=30,
)


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "external_account_id",
            name="uq_integration_connections_workspace_provider_account",
        ),
        Index(
            "ix_integration_connections_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        integration_provider_type,
        nullable=False,
    )
    status: Mapped[IntegrationConnectionStatus] = mapped_column(
        integration_connection_status_type,
        nullable=False,
        default=IntegrationConnectionStatus.ACTIVE,
    )
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    connected_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class IntegrationSubscription(Base):
    __tablename__ = "integration_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "event_type",
            name="uq_integration_subscriptions_connection_event",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[IntegrationEventType] = mapped_column(
        integration_event_type,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    destination_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
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


class IntegrationDelivery(Base):
    __tablename__ = "integration_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "event_type",
            "event_id",
            name="uq_integration_deliveries_connection_event",
        ),
        Index(
            "ix_integration_deliveries_retry_ready",
            "status",
            "next_retry_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[IntegrationEventType] = mapped_column(
        integration_event_type,
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[IntegrationDeliveryStatus] = mapped_column(
        integration_delivery_status_type,
        nullable=False,
        default=IntegrationDeliveryStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class IntegrationWebhookEvent(Base):
    __tablename__ = "integration_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_delivery_id",
            name="uq_integration_webhook_events_provider_delivery",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[IntegrationProvider] = mapped_column(
        integration_provider_type,
        nullable=False,
    )
    provider_delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[IntegrationWebhookStatus] = mapped_column(
        integration_webhook_status_type,
        nullable=False,
        default=IntegrationWebhookStatus.RECEIVED,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationOutboxEvent(Base):
    __tablename__ = "integration_outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "event_id",
            name="uq_integration_outbox_events_type_id",
        ),
        Index(
            "ix_integration_outbox_events_ready",
            "status",
            "available_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[IntegrationEventType] = mapped_column(
        integration_event_type,
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[IntegrationOutboxStatus] = mapped_column(
        integration_outbox_status_type,
        nullable=False,
        default=IntegrationOutboxStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
