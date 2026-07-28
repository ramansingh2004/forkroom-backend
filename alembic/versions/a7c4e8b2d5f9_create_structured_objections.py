"""Create structured objections and resolution history.

Revision ID: a7c4e8b2d5f9
Revises: f6a9c3d7e2b1
Create Date: 2026-07-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c4e8b2d5f9"
down_revision: str | None = "f6a9c3d7e2b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    objection_severity = sa.Enum(
        "informational",
        "major",
        "blocking",
        name="objection_severity",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
    objection_status = sa.Enum(
        "open",
        "resolved",
        "dismissed",
        name="objection_status",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
    event_status = sa.Enum(
        "open",
        "resolved",
        "dismissed",
        name="objection_event_status",
        native_enum=False,
        create_constraint=False,
        length=20,
    )

    op.create_table(
        "objections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("severity", objection_severity, nullable=False),
        sa.Column("status", objection_status, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            (
                "(status = 'open' AND resolution_note IS NULL "
                "AND resolved_by_id IS NULL AND resolved_at IS NULL) OR "
                "(status IN ('resolved', 'dismissed') AND resolution_note IS NOT NULL "
                "AND resolved_by_id IS NOT NULL AND resolved_at IS NOT NULL)"
            ),
            name="ck_objections_resolution_state",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_objections_created_by_id"),
        "objections",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_objections_proposal_id"),
        "objections",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_objections_severity"),
        "objections",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_objections_status"),
        "objections",
        ["status"],
        unique=False,
    )

    op.create_table(
        "objection_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("objection_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", event_status, nullable=False),
        sa.Column("to_status", event_status, nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["objection_id"],
            ["objections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_objection_status_events_actor_id"),
        "objection_status_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_objection_status_events_objection_id"),
        "objection_status_events",
        ["objection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_objection_status_events_objection_id"),
        table_name="objection_status_events",
    )
    op.drop_index(
        op.f("ix_objection_status_events_actor_id"),
        table_name="objection_status_events",
    )
    op.drop_table("objection_status_events")
    op.drop_index(
        op.f("ix_objections_status"),
        table_name="objections",
    )
    op.drop_index(
        op.f("ix_objections_severity"),
        table_name="objections",
    )
    op.drop_index(
        op.f("ix_objections_proposal_id"),
        table_name="objections",
    )
    op.drop_index(
        op.f("ix_objections_created_by_id"),
        table_name="objections",
    )
    op.drop_table("objections")
