"""Create review outcomes and immutable decision revision links.

Revision ID: f2b4c8e1a6d9
Revises: e1a3b7d9f2c4
Create Date: 2026-07-30 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b4c8e1a6d9"
down_revision: str | None = "e1a3b7d9f2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_decision_reviews_cancelled_state",
        "decision_reviews",
        type_="check",
    )
    op.drop_constraint("review_status", "decision_reviews", type_="check")
    op.add_column(
        "decision_reviews",
        sa.Column("outcome", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "decision_reviews",
        sa.Column("outcome_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "decision_reviews",
        sa.Column("completed_by_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "decision_reviews",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_decision_reviews_completed_by_id_users",
        "decision_reviews",
        "users",
        ["completed_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_decision_reviews_outcome"),
        "decision_reviews",
        ["outcome"],
        unique=False,
    )
    op.create_check_constraint(
        "review_status",
        "decision_reviews",
        "status IN ('scheduled', 'completed', 'cancelled')",
    )
    op.create_check_constraint(
        "review_outcome",
        "decision_reviews",
        "outcome IN ('confirmed', 'reopened', 'superseded')",
    )
    op.create_check_constraint(
        "ck_decision_reviews_terminal_state",
        "decision_reviews",
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
    )

    op.create_table(
        "decision_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("root_decision_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_decision_id", sa.Uuid(), nullable=False),
        sa.Column("successor_decision_id", sa.Uuid(), nullable=False),
        sa.Column("source_lock_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_decision_revisions_positive_number",
        ),
        sa.CheckConstraint(
            "outcome IN ('reopened', 'superseded')",
            name="ck_decision_revisions_outcome",
        ),
        sa.CheckConstraint(
            "outcome IN ('confirmed', 'reopened', 'superseded')",
            name="review_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["decision_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["root_decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_lock_id"],
            ["decision_locks.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["successor_decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "predecessor_decision_id",
            name="uq_decision_revisions_predecessor",
        ),
        sa.UniqueConstraint(
            "review_id",
            name="uq_decision_revisions_review",
        ),
        sa.UniqueConstraint(
            "root_decision_id",
            "revision_number",
            name="uq_decision_revisions_root_number",
        ),
        sa.UniqueConstraint(
            "successor_decision_id",
            name="uq_decision_revisions_successor",
        ),
    )
    for column in (
        "created_by_id",
        "predecessor_decision_id",
        "review_id",
        "root_decision_id",
        "source_lock_id",
        "successor_decision_id",
    ):
        op.create_index(
            op.f(f"ix_decision_revisions_{column}"),
            "decision_revisions",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "successor_decision_id",
        "source_lock_id",
        "root_decision_id",
        "review_id",
        "predecessor_decision_id",
        "created_by_id",
    ):
        op.drop_index(
            op.f(f"ix_decision_revisions_{column}"),
            table_name="decision_revisions",
        )
    op.drop_table("decision_revisions")

    op.drop_constraint(
        "ck_decision_reviews_terminal_state",
        "decision_reviews",
        type_="check",
    )
    op.drop_constraint("review_outcome", "decision_reviews", type_="check")
    op.drop_constraint("review_status", "decision_reviews", type_="check")
    op.drop_index(
        op.f("ix_decision_reviews_outcome"),
        table_name="decision_reviews",
    )
    op.drop_constraint(
        "fk_decision_reviews_completed_by_id_users",
        "decision_reviews",
        type_="foreignkey",
    )
    op.drop_column("decision_reviews", "completed_at")
    op.drop_column("decision_reviews", "completed_by_id")
    op.drop_column("decision_reviews", "outcome_rationale")
    op.drop_column("decision_reviews", "outcome")
    op.create_check_constraint(
        "review_status",
        "decision_reviews",
        "status IN ('scheduled', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_decision_reviews_cancelled_state",
        "decision_reviews",
        (
            "(status = 'scheduled' AND cancelled_at IS NULL "
            "AND cancelled_by_id IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancelled_by_id IS NOT NULL)"
        ),
    )
