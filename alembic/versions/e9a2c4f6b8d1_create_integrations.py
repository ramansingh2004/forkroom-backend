"""create integrations

Revision ID: e9a2c4f6b8d1
Revises: d6f8a1c4e7b9
Create Date: 2026-08-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e9a2c4f6b8d1"
down_revision: str | None = "d6f8a1c4e7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

provider = sa.Enum(
    "slack",
    name="integration_provider",
    native_enum=False,
    create_constraint=True,
    length=30,
)
connection_status = sa.Enum(
    "pending",
    "active",
    "expired",
    "revoked",
    "error",
    name="integration_connection_status",
    native_enum=False,
    create_constraint=True,
    length=30,
)
event_type = sa.Enum(
    "decision_activated",
    "voting_opened",
    "voting_closed",
    "decision_locked",
    "action_assigned",
    "review_due",
    "export_failed",
    name="integration_event_type",
    native_enum=False,
    create_constraint=True,
    length=40,
)
delivery_status = sa.Enum(
    "pending",
    "delivering",
    "retry_scheduled",
    "delivered",
    "failed",
    name="integration_delivery_status",
    native_enum=False,
    create_constraint=True,
    length=30,
)
webhook_status = sa.Enum(
    "received",
    "processing",
    "processed",
    "failed",
    name="integration_webhook_status",
    native_enum=False,
    create_constraint=True,
    length=30,
)
outbox_status = sa.Enum(
    "pending",
    "processing",
    "processed",
    "failed",
    name="integration_outbox_status",
    native_enum=False,
    create_constraint=True,
    length=30,
)


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", provider, nullable=False),
        sa.Column("status", connection_status, nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("external_account_name", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("connected_by_id", sa.Uuid(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["connected_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "external_account_id",
            name="uq_integration_connections_workspace_provider_account",
        ),
    )
    op.create_index(
        "ix_integration_connections_workspace_id",
        "integration_connections",
        ["workspace_id"],
    )
    op.create_index(
        "ix_integration_connections_connected_by_id",
        "integration_connections",
        ["connected_by_id"],
    )
    op.create_index(
        "ix_integration_connections_workspace_status",
        "integration_connections",
        ["workspace_id", "status"],
    )

    op.create_table(
        "integration_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("destination_id", sa.String(length=255), nullable=True),
        sa.Column("destination_name", sa.String(length=255), nullable=True),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "event_type",
            name="uq_integration_subscriptions_connection_event",
        ),
    )
    op.create_index(
        "ix_integration_subscriptions_connection_id",
        "integration_subscriptions",
        ["connection_id"],
    )

    op.create_table(
        "integration_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "request_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "event_type",
            "event_id",
            name="uq_integration_deliveries_connection_event",
        ),
    )
    op.create_index(
        "ix_integration_deliveries_connection_id",
        "integration_deliveries",
        ["connection_id"],
    )
    op.create_index(
        "ix_integration_deliveries_retry_ready",
        "integration_deliveries",
        ["status", "next_retry_at"],
    )

    op.create_table(
        "integration_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", provider, nullable=False),
        sa.Column("provider_delivery_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "signature_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("status", webhook_status, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_delivery_id",
            name="uq_integration_webhook_events_provider_delivery",
        ),
    )

    op.create_table(
        "integration_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", outbox_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type",
            "event_id",
            name="uq_integration_outbox_events_type_id",
        ),
    )
    op.create_index(
        "ix_integration_outbox_events_workspace_id",
        "integration_outbox_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_integration_outbox_events_ready",
        "integration_outbox_events",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_events_ready", table_name="integration_outbox_events")
    op.drop_index(
        "ix_integration_outbox_events_workspace_id",
        table_name="integration_outbox_events",
    )
    op.drop_table("integration_outbox_events")
    op.drop_table("integration_webhook_events")
    op.drop_index("ix_integration_deliveries_retry_ready", table_name="integration_deliveries")
    op.drop_index(
        "ix_integration_deliveries_connection_id",
        table_name="integration_deliveries",
    )
    op.drop_table("integration_deliveries")
    op.drop_index(
        "ix_integration_subscriptions_connection_id",
        table_name="integration_subscriptions",
    )
    op.drop_table("integration_subscriptions")
    op.drop_index(
        "ix_integration_connections_workspace_status",
        table_name="integration_connections",
    )
    op.drop_index(
        "ix_integration_connections_connected_by_id",
        table_name="integration_connections",
    )
    op.drop_index(
        "ix_integration_connections_workspace_id",
        table_name="integration_connections",
    )
    op.drop_table("integration_connections")
