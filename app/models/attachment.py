from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttachmentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    AVAILABLE = "available"
    REJECTED = "rejected"
    DELETED = "deleted"


attachment_status_type = Enum(
    AttachmentStatus,
    name="attachment_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_attachments_size_positive"),
        CheckConstraint("processing_attempts >= 0", name="ck_attachments_attempts_positive"),
        CheckConstraint(
            "NOT (decision_id IS NULL AND proposal_id IS NOT NULL)",
            name="ck_attachments_proposal_requires_decision",
        ),
        Index("ix_attachments_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    proposal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    uploaded_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[AttachmentStatus] = mapped_column(
        attachment_status_type,
        nullable=False,
        default=AttachmentStatus.PENDING,
        index=True,
    )
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
