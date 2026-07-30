from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CollaborationDocument(Base):
    __tablename__ = "collaboration_documents"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_collaboration_documents_proposal_id"),
        UniqueConstraint("document_name", name="uq_collaboration_documents_document_name"),
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
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ydoc_state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    state_version: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
