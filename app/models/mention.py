from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Mention(Base):
    __tablename__ = "mentions"
    __table_args__ = (
        CheckConstraint(
            "proposal_id IS NULL OR objection_id IS NULL",
            name="ck_mentions_single_context",
        ),
        UniqueConstraint(
            "comment_id",
            "mentioned_user_id",
            name="uq_mentions_comment_user",
        ),
        Index(
            "ix_mentions_user_read_created",
            "mentioned_user_id",
            "read_at",
            "created_at",
        ),
        Index(
            "ix_mentions_workspace_user_created",
            "workspace_id",
            "mentioned_user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    comment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mentioned_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mentioned_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
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
    )
    objection_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("objections.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
