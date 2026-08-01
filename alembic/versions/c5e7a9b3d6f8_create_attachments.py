"""Create attachment metadata and processing state.

Revision ID: c5e7a9b3d6f8
Revises: b4d6f8a2c5e7
Create Date: 2026-08-01 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5e7a9b3d6f8"
down_revision: str | None = "b4d6f8a2c5e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "available",
                "rejected",
                "deleted",
                name="attachment_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("processing_error", sa.String(length=1000), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("processing_attempts >= 0", name="ck_attachments_attempts_positive"),
        sa.CheckConstraint(
            "NOT (decision_id IS NULL AND proposal_id IS NOT NULL)",
            name="ck_attachments_proposal_requires_decision",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachments_size_positive"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    for column in (
        "decision_id",
        "proposal_id",
        "status",
        "uploaded_by_id",
        "workspace_id",
    ):
        op.create_index(
            op.f(f"ix_attachments_{column}"),
            "attachments",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_attachments_workspace_created",
        "attachments",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_workspace_created", table_name="attachments")
    for column in (
        "workspace_id",
        "uploaded_by_id",
        "status",
        "proposal_id",
        "decision_id",
    ):
        op.drop_index(op.f(f"ix_attachments_{column}"), table_name="attachments")
    op.drop_table("attachments")
