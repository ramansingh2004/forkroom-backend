"""create decision exports and search index

Revision ID: d6f8a1c4e7b9
Revises: c5e7a9b3d6f8
Create Date: 2026-08-01 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d6f8a1c4e7b9"
down_revision: str | None = "c5e7a9b3d6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("decision_lock_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=700), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_decision_exports_attempt_count"),
        sa.CheckConstraint(
            "(status = 'available' AND completed_at IS NOT NULL AND size_bytes IS NOT NULL) "
            "OR (status <> 'available' AND completed_at IS NULL)",
            name="ck_decision_exports_available_state",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'available', 'failed')",
            name="export_status",
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_lock_id"], ["decision_locks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_lock_id", name="uq_decision_exports_lock"),
        sa.UniqueConstraint("object_key", name="uq_decision_exports_object_key"),
    )
    op.create_index("ix_decision_exports_workspace_id", "decision_exports", ["workspace_id"])
    op.create_index("ix_decision_exports_decision_id", "decision_exports", ["decision_id"])
    op.create_index("ix_decision_exports_status", "decision_exports", ["status"])

    op.create_table(
        "decision_search_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("decision_status", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(body, '')), 'B')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", name="uq_decision_search_documents_decision"),
    )
    op.create_index(
        "ix_decision_search_documents_vector",
        "decision_search_documents",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_decision_search_documents_workspace_id",
        "decision_search_documents",
        ["workspace_id"],
    )
    op.create_index(
        "ix_decision_search_documents_status",
        "decision_search_documents",
        ["decision_status"],
    )
    op.create_index(
        "ix_decision_search_documents_category",
        "decision_search_documents",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_search_documents_category", table_name="decision_search_documents")
    op.drop_index("ix_decision_search_documents_status", table_name="decision_search_documents")
    op.drop_index(
        "ix_decision_search_documents_workspace_id", table_name="decision_search_documents"
    )
    op.drop_index("ix_decision_search_documents_vector", table_name="decision_search_documents")
    op.drop_table("decision_search_documents")
    op.drop_index("ix_decision_exports_status", table_name="decision_exports")
    op.drop_index("ix_decision_exports_decision_id", table_name="decision_exports")
    op.drop_index("ix_decision_exports_workspace_id", table_name="decision_exports")
    op.drop_table("decision_exports")
