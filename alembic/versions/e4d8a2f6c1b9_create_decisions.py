"""Create workspace decisions.

Revision ID: e4d8a2f6c1b9
Revises: b3c7e1a4d9f2
Create Date: 2026-07-28 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4d8a2f6c1b9"
down_revision: str | None = "b3c7e1a4d9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    decision_category = sa.Enum(
        "technology",
        "architecture",
        "delivery",
        "team_process",
        "other",
        name="decision_category",
        native_enum=False,
        create_constraint=True,
        length=30,
    )
    decision_status = sa.Enum(
        "draft",
        "active",
        "closed",
        "archived",
        name="decision_status",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", decision_category, nullable=False),
        sa.Column("status", decision_status, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decisions_created_by_id"),
        "decisions",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decisions_status"),
        "decisions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decisions_workspace_id"),
        "decisions",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_decisions_workspace_id"),
        table_name="decisions",
    )
    op.drop_index(
        op.f("ix_decisions_status"),
        table_name="decisions",
    )
    op.drop_index(
        op.f("ix_decisions_created_by_id"),
        table_name="decisions",
    )
    op.drop_table("decisions")
