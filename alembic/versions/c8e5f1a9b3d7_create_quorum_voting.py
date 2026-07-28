"""Create quorum voting sessions, eligibility snapshots, and ballots.

Revision ID: c8e5f1a9b3d7
Revises: a7c4e8b2d5f9
Create Date: 2026-07-29 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e5f1a9b3d7"
down_revision: str | None = "a7c4e8b2d5f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    voting_status = sa.Enum(
        "draft",
        "open",
        "closed",
        "cancelled",
        name="voting_session_status",
        native_enum=False,
        create_constraint=True,
        length=20,
    )

    op.create_table(
        "voting_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("status", voting_status, nullable=False),
        sa.Column("quorum_percentage", sa.Integer(), nullable=False),
        sa.Column("eligible_voter_count", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "quorum_percentage >= 1 AND quorum_percentage <= 100",
            name="ck_voting_sessions_quorum_percentage",
        ),
        sa.CheckConstraint(
            "eligible_voter_count >= 0",
            name="ck_voting_sessions_eligible_voter_count",
        ),
        sa.CheckConstraint(
            (
                "(status = 'draft' AND opened_at IS NULL AND closed_at IS NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'open' AND opened_at IS NOT NULL AND closed_at IS NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'closed' AND opened_at IS NOT NULL AND closed_at IS NOT NULL "
                "AND cancelled_at IS NULL) OR "
                "(status = 'cancelled' AND closed_at IS NULL AND cancelled_at IS NOT NULL)"
            ),
            name="ck_voting_sessions_status_timestamps",
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
        op.f("ix_voting_sessions_created_by_id"),
        "voting_sessions",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_voting_sessions_decision_id"),
        "voting_sessions",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_voting_sessions_status"),
        "voting_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_voting_sessions_one_unfinished_per_decision",
        "voting_sessions",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'open')"),
    )

    op.create_table(
        "voting_eligible_voters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("voting_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voting_session_id"],
            ["voting_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voting_session_id",
            "user_id",
            name="uq_voting_eligible_voters_session_user",
        ),
    )
    op.create_index(
        op.f("ix_voting_eligible_voters_user_id"),
        "voting_eligible_voters",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_voting_eligible_voters_voting_session_id"),
        "voting_eligible_voters",
        ["voting_session_id"],
        unique=False,
    )

    op.create_table(
        "voting_session_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("voting_session_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voting_session_id"],
            ["voting_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voting_session_id",
            "proposal_id",
            name="uq_voting_session_proposals_session_proposal",
        ),
    )
    op.create_index(
        op.f("ix_voting_session_proposals_proposal_id"),
        "voting_session_proposals",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_voting_session_proposals_voting_session_id"),
        "voting_session_proposals",
        ["voting_session_id"],
        unique=False,
    )

    op.create_table(
        "votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("voting_session_id", sa.Uuid(), nullable=False),
        sa.Column("voter_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voter_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voting_session_id"],
            ["voting_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voting_session_id",
            "voter_id",
            name="uq_votes_session_voter",
        ),
    )
    op.create_index(
        op.f("ix_votes_proposal_id"),
        "votes",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_votes_voter_id"),
        "votes",
        ["voter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_votes_voting_session_id"),
        "votes",
        ["voting_session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_votes_voting_session_id"), table_name="votes")
    op.drop_index(op.f("ix_votes_voter_id"), table_name="votes")
    op.drop_index(op.f("ix_votes_proposal_id"), table_name="votes")
    op.drop_table("votes")
    op.drop_index(
        op.f("ix_voting_session_proposals_voting_session_id"),
        table_name="voting_session_proposals",
    )
    op.drop_index(
        op.f("ix_voting_session_proposals_proposal_id"),
        table_name="voting_session_proposals",
    )
    op.drop_table("voting_session_proposals")
    op.drop_index(
        op.f("ix_voting_eligible_voters_voting_session_id"),
        table_name="voting_eligible_voters",
    )
    op.drop_index(
        op.f("ix_voting_eligible_voters_user_id"),
        table_name="voting_eligible_voters",
    )
    op.drop_table("voting_eligible_voters")
    op.drop_index(
        "uq_voting_sessions_one_unfinished_per_decision",
        table_name="voting_sessions",
    )
    op.drop_index(
        op.f("ix_voting_sessions_status"),
        table_name="voting_sessions",
    )
    op.drop_index(
        op.f("ix_voting_sessions_decision_id"),
        table_name="voting_sessions",
    )
    op.drop_index(
        op.f("ix_voting_sessions_created_by_id"),
        table_name="voting_sessions",
    )
    op.drop_table("voting_sessions")
