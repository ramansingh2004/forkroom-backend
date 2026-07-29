"""Create owned implementation actions and scheduled decision reviews.

Revision ID: e1a3b7d9f2c4
Revises: d9f2a6c4e8b1
Create Date: 2026-07-29 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a3b7d9f2c4"
down_revision: str | None = "d9f2a6c4e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "implementation_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('todo', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="action_status",
        ),
        sa.CheckConstraint(
            (
                "(status = 'completed' AND completed_at IS NOT NULL) OR "
                "(status <> 'completed' AND completed_at IS NULL)"
            ),
            name="ck_implementation_actions_completed_state",
        ),
        sa.CheckConstraint(
            (
                "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR "
                "(status <> 'cancelled' AND cancelled_at IS NULL)"
            ),
            name="ck_implementation_actions_cancelled_state",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_implementation_actions_assignee_id"),
        "implementation_actions",
        ["assignee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_implementation_actions_created_by_id"),
        "implementation_actions",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_implementation_actions_decision_id"),
        "implementation_actions",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_implementation_actions_status"),
        "implementation_actions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "decision_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_by_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancelled_by_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled')",
            name="review_status",
        ),
        sa.CheckConstraint(
            (
                "(status = 'scheduled' AND cancelled_at IS NULL "
                "AND cancelled_by_id IS NULL) OR "
                "(status = 'cancelled' AND cancelled_at IS NOT NULL "
                "AND cancelled_by_id IS NOT NULL)"
            ),
            name="ck_decision_reviews_cancelled_state",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decision_reviews_decision_id"),
        "decision_reviews",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_reviews_scheduled_by_id"),
        "decision_reviews",
        ["scheduled_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_reviews_scheduled_for"),
        "decision_reviews",
        ["scheduled_for"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_reviews_status"),
        "decision_reviews",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_decision_reviews_one_scheduled_per_decision",
        "decision_reviews",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_decision_reviews_one_scheduled_per_decision",
        table_name="decision_reviews",
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.drop_index(op.f("ix_decision_reviews_status"), table_name="decision_reviews")
    op.drop_index(
        op.f("ix_decision_reviews_scheduled_for"),
        table_name="decision_reviews",
    )
    op.drop_index(
        op.f("ix_decision_reviews_scheduled_by_id"),
        table_name="decision_reviews",
    )
    op.drop_index(
        op.f("ix_decision_reviews_decision_id"),
        table_name="decision_reviews",
    )
    op.drop_table("decision_reviews")

    op.drop_index(
        op.f("ix_implementation_actions_status"),
        table_name="implementation_actions",
    )
    op.drop_index(
        op.f("ix_implementation_actions_decision_id"),
        table_name="implementation_actions",
    )
    op.drop_index(
        op.f("ix_implementation_actions_created_by_id"),
        table_name="implementation_actions",
    )
    op.drop_index(
        op.f("ix_implementation_actions_assignee_id"),
        table_name="implementation_actions",
    )
    op.drop_table("implementation_actions")
