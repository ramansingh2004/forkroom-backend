"""Create collaborative Yjs document persistence.

Revision ID: a3c5e7f9b1d4
Revises: f2b4c8e1a6d9
Create Date: 2026-07-30 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c5e7f9b1d4"
down_revision: str | None = "f2b4c8e1a6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collaboration_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("document_name", sa.String(length=100), nullable=False),
        sa.Column("ydoc_state", sa.LargeBinary(), nullable=True),
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_name", name="uq_collaboration_documents_document_name"),
        sa.UniqueConstraint("proposal_id", name="uq_collaboration_documents_proposal_id"),
    )
    for column in ("workspace_id", "decision_id", "proposal_id"):
        op.create_index(
            op.f(f"ix_collaboration_documents_{column}"),
            "collaboration_documents",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("proposal_id", "decision_id", "workspace_id"):
        op.drop_index(
            op.f(f"ix_collaboration_documents_{column}"),
            table_name="collaboration_documents",
        )
    op.drop_table("collaboration_documents")
