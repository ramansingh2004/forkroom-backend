from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DecisionLockConflictError
from app.models.decision import Decision, DecisionLock, DecisionStatus


class DecisionLockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_decision(self, decision_id: UUID) -> DecisionLock | None:
        statement = select(DecisionLock).where(DecisionLock.decision_id == decision_id)
        return cast(DecisionLock | None, await self._session.scalar(statement))

    async def create(
        self,
        decision_lock: DecisionLock,
        decision: Decision,
        *,
        locked_at: datetime,
    ) -> DecisionLock:
        decision.status = DecisionStatus.LOCKED
        decision.closed_at = locked_at
        decision.locked_at = locked_at
        self._session.add(decision_lock)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise DecisionLockConflictError from error
        await self._session.refresh(decision_lock)
        return decision_lock
