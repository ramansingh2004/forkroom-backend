from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment, AttachmentStatus


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, attachment: Attachment) -> Attachment:
        self._session.add(attachment)
        await self._session.commit()
        await self._session.refresh(attachment)
        return attachment

    async def get(self, workspace_id: UUID, attachment_id: UUID) -> Attachment | None:
        statement = select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.workspace_id == workspace_id,
            Attachment.status != AttachmentStatus.DELETED,
        )
        return cast(Attachment | None, await self._session.scalar(statement))

    async def get_by_id(self, attachment_id: UUID) -> Attachment | None:
        return await self._session.get(Attachment, attachment_id)

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        decision_id: UUID | None,
        proposal_id: UUID | None,
    ) -> list[Attachment]:
        statement = select(Attachment).where(
            Attachment.workspace_id == workspace_id,
            Attachment.status != AttachmentStatus.DELETED,
        )
        if decision_id is not None:
            statement = statement.where(Attachment.decision_id == decision_id)
        if proposal_id is not None:
            statement = statement.where(Attachment.proposal_id == proposal_id)
        statement = statement.order_by(Attachment.created_at.desc())
        return list((await self._session.scalars(statement)).all())

    async def update(
        self,
        attachment: Attachment,
        *,
        values: dict[str, object],
    ) -> Attachment:
        for field, value in values.items():
            setattr(attachment, field, value)
        await self._session.commit()
        await self._session.refresh(attachment)
        return attachment

    async def claim_processing(self, attachment_id: UUID) -> Attachment | None:
        attachment = await self.get_by_id(attachment_id)
        if attachment is None or attachment.status is not AttachmentStatus.PROCESSING:
            return None
        attachment.processing_attempts += 1
        await self._session.commit()
        await self._session.refresh(attachment)
        return attachment

    async def list_processing(self, *, limit: int = 100) -> list[Attachment]:
        statement = (
            select(Attachment)
            .where(Attachment.status == AttachmentStatus.PROCESSING)
            .order_by(Attachment.updated_at.asc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def mark_available(
        self,
        attachment: Attachment,
        *,
        sha256: str,
        processed_at: datetime,
    ) -> Attachment:
        return await self.update(
            attachment,
            values={
                "status": AttachmentStatus.AVAILABLE,
                "sha256": sha256,
                "processed_at": processed_at,
                "processing_error": None,
            },
        )

    async def mark_rejected(
        self,
        attachment: Attachment,
        *,
        error: str,
        processed_at: datetime,
    ) -> Attachment:
        return await self.update(
            attachment,
            values={
                "status": AttachmentStatus.REJECTED,
                "processing_error": error[:1000],
                "processed_at": processed_at,
            },
        )
