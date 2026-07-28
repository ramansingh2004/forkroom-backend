"""Add user authentication version.

Revision ID: 9f1b27d4a6c8
Revises: cf6259873ee8
Create Date: 2026-07-27 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9f1b27d4a6c8"
down_revision: str | None = "cf6259873ee8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_version")
