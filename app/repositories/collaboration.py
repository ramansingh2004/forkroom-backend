from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import CollaborationDocument


class CollaborationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_proposal(self, proposal_id: UUID) -> CollaborationDocument | None:
        statement = select(CollaborationDocument).where(
            CollaborationDocument.proposal_id == proposal_id
        )
        return cast(CollaborationDocument | None, await self._session.scalar(statement))

    async def get_or_create(
        self,
        *,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> CollaborationDocument:
        existing = await self.get_for_proposal(proposal_id)
        if existing is not None:
            return existing
        document = CollaborationDocument(
            workspace_id=workspace_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
            document_name=f"proposal:{proposal_id}",
            state_version=0,
        )
        self._session.add(document)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_for_proposal(proposal_id)
            if existing is None:
                raise
            return existing
        await self._session.refresh(document)
        return document
