"""Create durable notifications and delivery tracking.

Revision ID: b4d6f8a2c5e7
Revises: a3c5e7f9b1d4
Create Date: 2026-07-31 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4d6f8a2c5e7"
down_revision: str | None = "a3c5e7f9b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("attempt_count >= 0", name="ck_notifications_attempt_count"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_notifications_max_attempts"),
        sa.CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_notifications_attempt_limit",
        ),
        sa.CheckConstraint(
            (
                "(status = 'delivered' AND delivered_at IS NOT NULL AND failed_at IS NULL) OR "
                "(status = 'failed' AND failed_at IS NOT NULL AND delivered_at IS NULL) OR "
                "(status IN ('pending', 'delivering', 'retry_scheduled') "
                "AND delivered_at IS NULL AND failed_at IS NULL)"
            ),
            name="ck_notifications_terminal_state",
        ),
        sa.CheckConstraint(
            "kind IN ('action_due', 'decision_review', 'decision_deadline', 'voting_close')",
            name="notification_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'delivering', 'retry_scheduled', 'delivered', 'failed')",
            name="notification_status",
        ),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_notifications_idempotency_key"),
    )
    for column in ("recipient_id", "workspace_id", "kind", "source_id"):
        op.create_index(
            op.f(f"ix_notifications_{column}"),
            "notifications",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_notifications_delivery_ready",
        "notifications",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_index("ix_notifications_delivery_ready", table_name="notifications")
    for column in ("source_id", "kind", "workspace_id", "recipient_id"):
        op.drop_index(op.f(f"ix_notifications_{column}"), table_name="notifications")
    op.drop_table("notifications")
