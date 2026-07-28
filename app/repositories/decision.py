from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision import Decision, DecisionCategory, DecisionStatus


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, decision: Decision) -> Decision:
        self._session.add(decision)
        await self._session.commit()
        await self._session.refresh(decision)
        return decision

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        status: DecisionStatus | None,
        category: DecisionCategory | None,
        limit: int,
        offset: int,
    ) -> list[Decision]:
        statement = select(Decision).where(Decision.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(Decision.status == status)
        if category is not None:
            statement = statement.where(Decision.category == category)
        statement = statement.order_by(Decision.updated_at.desc()).limit(limit).offset(offset)
        return list((await self._session.scalars(statement)).all())

    async def get_for_workspace(
        self,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> Decision | None:
        statement = select(Decision).where(
            Decision.id == decision_id,
            Decision.workspace_id == workspace_id,
        )
        return cast(
            Decision | None,
            await self._session.scalar(statement),
        )

    async def update(
        self,
        decision: Decision,
        *,
        values: dict[str, object],
    ) -> Decision:
        for field, value in values.items():
            setattr(decision, field, value)
        await self._session.commit()
        await self._session.refresh(decision)
        return decision

    async def transition(
        self,
        decision: Decision,
        *,
        status: DecisionStatus,
        closed_at: datetime | None,
        archived_at: datetime | None,
    ) -> Decision:
        decision.status = status
        decision.closed_at = closed_at
        decision.archived_at = archived_at
        await self._session.commit()
        await self._session.refresh(decision)
        return decision

    async def delete(self, decision: Decision) -> None:
        await self._session.delete(decision)
        await self._session.commit()
