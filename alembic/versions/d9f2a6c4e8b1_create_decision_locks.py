"""Create immutable decision lock records.

Revision ID: d9f2a6c4e8b1
Revises: c8e5f1a9b3d7
Create Date: 2026-07-29 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9f2a6c4e8b1"
down_revision: str | None = "c8e5f1a9b3d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("decision_status", "decisions", type_="check")
    op.create_check_constraint(
        "decision_status",
        "decisions",
        "status IN ('draft', 'active', 'closed', 'locked', 'archived')",
    )
    op.add_column(
        "decisions",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_decisions_locked_state",
        "decisions",
        (
            "(status = 'locked' AND locked_at IS NOT NULL) OR "
            "(status <> 'locked' AND locked_at IS NULL)"
        ),
    )

    op.create_table(
        "decision_locks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("voting_session_id", sa.Uuid(), nullable=False),
        sa.Column("winning_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("locked_by_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(document_hash) = 64",
            name="ck_decision_locks_document_hash_length",
        ),
        sa.CheckConstraint(
            "snapshot_version >= 1",
            name="ck_decision_locks_snapshot_version",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["locked_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voting_session_id"],
            ["voting_sessions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["winning_proposal_id"],
            ["proposals.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            name="uq_decision_locks_decision_id",
        ),
        sa.UniqueConstraint(
            "voting_session_id",
            name="uq_decision_locks_voting_session_id",
        ),
    )
    op.create_index(
        op.f("ix_decision_locks_decision_id"),
        "decision_locks",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_locks_locked_by_id"),
        "decision_locks",
        ["locked_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_locks_voting_session_id"),
        "decision_locks",
        ["voting_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_decision_locks_winning_proposal_id"),
        "decision_locks",
        ["winning_proposal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_decision_locks_winning_proposal_id"),
        table_name="decision_locks",
    )
    op.drop_index(
        op.f("ix_decision_locks_voting_session_id"),
        table_name="decision_locks",
    )
    op.drop_index(
        op.f("ix_decision_locks_locked_by_id"),
        table_name="decision_locks",
    )
    op.drop_index(
        op.f("ix_decision_locks_decision_id"),
        table_name="decision_locks",
    )
    op.drop_table("decision_locks")
    op.drop_constraint("ck_decisions_locked_state", "decisions", type_="check")
    op.execute(
        "UPDATE decisions SET status = 'closed', closed_at = COALESCE(closed_at, locked_at) "
        "WHERE status = 'locked'"
    )
    op.drop_column("decisions", "locked_at")
    op.drop_constraint("decision_status", "decisions", type_="check")
    op.create_check_constraint(
        "decision_status",
        "decisions",
        "status IN ('draft', 'active', 'closed', 'archived')",
    )
