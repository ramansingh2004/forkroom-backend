"""Create proposals and comparison criteria.

Revision ID: f6a9c3d7e2b1
Revises: e4d8a2f6c1b9
Create Date: 2026-07-28 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a9c3d7e2b1"
down_revision: str | None = "e4d8a2f6c1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    proposal_status = sa.Enum(
        "draft",
        "submitted",
        "withdrawn",
        name="proposal_status",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
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
            ["decision_id"],
            ["decisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_proposals_created_by_id"),
        "proposals",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_proposals_decision_id"),
        "proposals",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_proposals_status"),
        "proposals",
        ["status"],
        unique=False,
    )

    op.create_table(
        "decision_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
            "position >= 0",
            name="ck_decision_criteria_position",
        ),
        sa.CheckConstraint(
            "weight >= 1 AND weight <= 100",
            name="ck_decision_criteria_weight",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            "position",
            name="uq_decision_criteria_decision_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        op.f("ix_decision_criteria_decision_id"),
        "decision_criteria",
        ["decision_id"],
        unique=False,
    )

    op.create_table(
        "proposal_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("scored_by_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=True),
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
            "score >= 1 AND score <= 5",
            name="ck_proposal_scores_score",
        ),
        sa.ForeignKeyConstraint(
            ["criterion_id"],
            ["decision_criteria.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scored_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id",
            "criterion_id",
            name="uq_proposal_scores_proposal_criterion",
        ),
    )
    op.create_index(
        op.f("ix_proposal_scores_criterion_id"),
        "proposal_scores",
        ["criterion_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_proposal_scores_proposal_id"),
        "proposal_scores",
        ["proposal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_proposal_scores_proposal_id"),
        table_name="proposal_scores",
    )
    op.drop_index(
        op.f("ix_proposal_scores_criterion_id"),
        table_name="proposal_scores",
    )
    op.drop_table("proposal_scores")
    op.drop_index(
        op.f("ix_decision_criteria_decision_id"),
        table_name="decision_criteria",
    )
    op.drop_table("decision_criteria")
    op.drop_index(
        op.f("ix_proposals_status"),
        table_name="proposals",
    )
    op.drop_index(
        op.f("ix_proposals_decision_id"),
        table_name="proposals",
    )
    op.drop_index(
        op.f("ix_proposals_created_by_id"),
        table_name="proposals",
    )
    op.drop_table("proposals")
