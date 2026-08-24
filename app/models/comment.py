from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            "proposal_id IS NULL OR objection_id IS NULL",
            name="ck_comments_single_context",
        ),
        Index("ix_comments_decision_created", "decision_id", "created_at"),
        Index("ix_comments_workspace_decision", "workspace_id", "decision_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    objection_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("objections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    structured_body: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
