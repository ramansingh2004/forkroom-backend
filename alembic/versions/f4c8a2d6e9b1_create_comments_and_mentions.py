"""Create structured comments and user mentions.

Revision ID: f4c8a2d6e9b1
Revises: e9a2c4f6b8d1
Create Date: 2026-08-24 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4c8a2d6e9b1"
down_revision: str | None = "e9a2c4f6b8d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("objection_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("structured_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "proposal_id IS NULL OR objection_id IS NULL",
            name="ck_comments_single_context",
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["objection_id"], ["objections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "workspace_id",
        "decision_id",
        "proposal_id",
        "objection_id",
        "author_id",
    ):
        op.create_index(op.f(f"ix_comments_{column}"), "comments", [column])
    op.create_index(
        "ix_comments_decision_created",
        "comments",
        ["decision_id", "created_at"],
    )
    op.create_index(
        "ix_comments_workspace_decision",
        "comments",
        ["workspace_id", "decision_id"],
    )

    op.create_table(
        "mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("comment_id", sa.Uuid(), nullable=False),
        sa.Column("mentioned_user_id", sa.Uuid(), nullable=False),
        sa.Column("mentioned_by_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("objection_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "proposal_id IS NULL OR objection_id IS NULL",
            name="ck_mentions_single_context",
        ),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mentioned_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mentioned_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["objection_id"], ["objections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comment_id",
            "mentioned_user_id",
            name="uq_mentions_comment_user",
        ),
    )
    for column in (
        "workspace_id",
        "comment_id",
        "mentioned_user_id",
        "mentioned_by_id",
        "decision_id",
    ):
        op.create_index(op.f(f"ix_mentions_{column}"), "mentions", [column])
    op.create_index(
        "ix_mentions_user_read_created",
        "mentions",
        ["mentioned_user_id", "read_at", "created_at"],
    )
    op.create_index(
        "ix_mentions_workspace_user_created",
        "mentions",
        ["workspace_id", "mentioned_user_id", "created_at"],
    )

    op.drop_constraint("notification_kind", "notifications", type_="check")
    op.create_check_constraint(
        "notification_kind",
        "notifications",
        "kind IN ('action_due', 'decision_review', 'decision_deadline', 'voting_close', 'mention')",
    )
    op.add_column("notifications", sa.Column("actor_id", sa.Uuid(), nullable=True))
    op.add_column("notifications", sa.Column("entity_type", sa.String(length=50), nullable=True))
    op.add_column("notifications", sa.Column("entity_id", sa.Uuid(), nullable=True))
    op.add_column("notifications", sa.Column("action_url", sa.String(length=2048), nullable=True))
    op.create_foreign_key(
        "fk_notifications_actor_id_users",
        "notifications",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_notifications_actor_id"), "notifications", ["actor_id"])
    op.create_index(op.f("ix_notifications_entity_id"), "notifications", ["entity_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_entity_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_actor_id"), table_name="notifications")
    op.drop_constraint("fk_notifications_actor_id_users", "notifications", type_="foreignkey")
    op.drop_column("notifications", "action_url")
    op.drop_column("notifications", "entity_id")
    op.drop_column("notifications", "entity_type")
    op.drop_column("notifications", "actor_id")
    op.drop_constraint("notification_kind", "notifications", type_="check")
    op.create_check_constraint(
        "notification_kind",
        "notifications",
        "kind IN ('action_due', 'decision_review', 'decision_deadline', 'voting_close')",
    )

    op.drop_index("ix_mentions_workspace_user_created", table_name="mentions")
    op.drop_index("ix_mentions_user_read_created", table_name="mentions")
    for column in (
        "decision_id",
        "mentioned_by_id",
        "mentioned_user_id",
        "comment_id",
        "workspace_id",
    ):
        op.drop_index(op.f(f"ix_mentions_{column}"), table_name="mentions")
    op.drop_table("mentions")

    op.drop_index("ix_comments_workspace_decision", table_name="comments")
    op.drop_index("ix_comments_decision_created", table_name="comments")
    for column in (
        "author_id",
        "objection_id",
        "proposal_id",
        "decision_id",
        "workspace_id",
    ):
        op.drop_index(op.f(f"ix_comments_{column}"), table_name="comments")
    op.drop_table("comments")
