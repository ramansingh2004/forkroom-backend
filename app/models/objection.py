from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ObjectionSeverity(StrEnum):
    INFORMATIONAL = "informational"
    MAJOR = "major"
    BLOCKING = "blocking"


class ObjectionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


objection_severity_type = Enum(
    ObjectionSeverity,
    name="objection_severity",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)

objection_status_type = Enum(
    ObjectionStatus,
    name="objection_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=True,
    length=20,
)

objection_event_status_type = Enum(
    ObjectionStatus,
    name="objection_event_status",
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    create_constraint=False,
    length=20,
)


class Objection(Base):
    __tablename__ = "objections"
    __table_args__ = (
        CheckConstraint(
            (
                "(status = 'open' AND resolution_note IS NULL "
                "AND resolved_by_id IS NULL AND resolved_at IS NULL) OR "
                "(status IN ('resolved', 'dismissed') AND resolution_note IS NOT NULL "
                "AND resolved_by_id IS NOT NULL AND resolved_at IS NOT NULL)"
            ),
            name="ck_objections_resolution_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    severity: Mapped[ObjectionSeverity] = mapped_column(
        objection_severity_type,
        nullable=False,
        index=True,
    )
    status: Mapped[ObjectionStatus] = mapped_column(
        objection_status_type,
        nullable=False,
        default=ObjectionStatus.OPEN,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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


class ObjectionStatusEvent(Base):
    __tablename__ = "objection_status_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    objection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("objections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[ObjectionStatus] = mapped_column(
        objection_event_status_type,
        nullable=False,
    )
    to_status: Mapped[ObjectionStatus] = mapped_column(
        objection_event_status_type,
        nullable=False,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
