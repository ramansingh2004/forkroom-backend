from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.objection import (
    Objection,
    ObjectionSeverity,
    ObjectionStatus,
    ObjectionStatusEvent,
)
from app.models.proposal import Proposal


class ObjectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, objection: Objection) -> Objection:
        self._session.add(objection)
        await self._session.commit()
        await self._session.refresh(objection)
        return objection

    async def list_for_proposal(
        self,
        proposal_id: UUID,
        *,
        severity: ObjectionSeverity | None,
        status: ObjectionStatus | None,
    ) -> list[Objection]:
        statement = select(Objection).where(Objection.proposal_id == proposal_id)
        if severity is not None:
            statement = statement.where(Objection.severity == severity)
        if status is not None:
            statement = statement.where(Objection.status == status)
        statement = statement.order_by(Objection.created_at.desc())
        return list((await self._session.scalars(statement)).all())

    async def get_for_proposal(
        self,
        proposal_id: UUID,
        objection_id: UUID,
    ) -> Objection | None:
        statement = select(Objection).where(
            Objection.id == objection_id,
            Objection.proposal_id == proposal_id,
        )
        return cast(Objection | None, await self._session.scalar(statement))

    async def update(
        self,
        objection: Objection,
        *,
        values: dict[str, object],
    ) -> Objection:
        for field, value in values.items():
            setattr(objection, field, value)
        await self._session.commit()
        await self._session.refresh(objection)
        return objection

    async def transition(
        self,
        objection: Objection,
        *,
        actor_id: UUID,
        status: ObjectionStatus,
        note: str,
        resolved_at: datetime | None,
    ) -> Objection:
        previous_status = objection.status
        objection.status = status
        objection.resolution_note = note if status is not ObjectionStatus.OPEN else None
        objection.resolved_by_id = actor_id if status is not ObjectionStatus.OPEN else None
        objection.resolved_at = resolved_at
        self._session.add(
            ObjectionStatusEvent(
                objection_id=objection.id,
                actor_id=actor_id,
                from_status=previous_status,
                to_status=status,
                note=note,
            )
        )
        await self._session.commit()
        await self._session.refresh(objection)
        return objection

    async def list_status_events(
        self,
        objection_id: UUID,
    ) -> list[ObjectionStatusEvent]:
        statement = (
            select(ObjectionStatusEvent)
            .where(ObjectionStatusEvent.objection_id == objection_id)
            .order_by(ObjectionStatusEvent.created_at.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def has_open_blocking_for_decision(self, decision_id: UUID) -> bool:
        statement = select(
            exists().where(
                Objection.proposal_id == Proposal.id,
                Proposal.decision_id == decision_id,
                Objection.severity == ObjectionSeverity.BLOCKING,
                Objection.status == ObjectionStatus.OPEN,
            )
        )
        return bool(await self._session.scalar(statement))
