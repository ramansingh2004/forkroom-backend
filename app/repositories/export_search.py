from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision import Decision, DecisionLock
from app.models.export_search import DecisionExport, DecisionSearchDocument, ExportStatus
from app.models.proposal import Proposal


@dataclass(frozen=True, slots=True)
class SearchResultRecord:
    decision_id: UUID
    title: str
    status: str
    category: str
    headline: str
    rank: float
    indexed_at: datetime


class DecisionExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_lock(self, lock_id: UUID) -> DecisionExport | None:
        statement = select(DecisionExport).where(DecisionExport.decision_lock_id == lock_id)
        return cast(DecisionExport | None, await self._session.scalar(statement))

    async def get_for_decision(self, decision_id: UUID) -> DecisionExport | None:
        statement = select(DecisionExport).where(DecisionExport.decision_id == decision_id)
        return cast(DecisionExport | None, await self._session.scalar(statement))

    async def get_by_id(self, export_id: UUID) -> DecisionExport | None:
        return await self._session.get(DecisionExport, export_id)

    async def create(self, export: DecisionExport) -> DecisionExport:
        self._session.add(export)
        await self._session.commit()
        await self._session.refresh(export)
        return export

    async def reset_failed(self, export: DecisionExport) -> DecisionExport:
        export.status = ExportStatus.PENDING
        export.attempt_count = 0
        export.error = None
        export.started_at = None
        await self._session.commit()
        await self._session.refresh(export)
        return export

    async def claim(self, export_id: UUID, now: datetime) -> DecisionExport | None:
        stale_before = now - timedelta(minutes=15)
        statement = (
            select(DecisionExport)
            .where(
                DecisionExport.id == export_id,
                or_(
                    DecisionExport.status.in_([ExportStatus.PENDING, ExportStatus.FAILED]),
                    (
                        (DecisionExport.status == ExportStatus.PROCESSING)
                        & (DecisionExport.started_at < stale_before)
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
        )
        export = cast(DecisionExport | None, await self._session.scalar(statement))
        if export is None:
            return None
        export.status = ExportStatus.PROCESSING
        export.started_at = now
        export.completed_at = None
        export.error = None
        export.attempt_count += 1
        await self._session.commit()
        await self._session.refresh(export)
        return export

    async def mark_available(
        self,
        export: DecisionExport,
        *,
        size_bytes: int,
        completed_at: datetime,
    ) -> None:
        export.status = ExportStatus.AVAILABLE
        export.size_bytes = size_bytes
        export.completed_at = completed_at
        export.error = None
        await self._session.commit()

    async def mark_failed(self, export: DecisionExport, error: str) -> None:
        export.status = ExportStatus.FAILED
        export.completed_at = None
        export.error = error[:4000]
        await self._session.commit()

    async def list_incomplete(self) -> list[DecisionExport]:
        statement = select(DecisionExport).where(
            DecisionExport.status.in_([ExportStatus.PENDING, ExportStatus.PROCESSING])
        )
        return list((await self._session.scalars(statement)).all())


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_stale_decision_ids(self, limit: int = 200) -> list[UUID]:
        latest_proposal = (
            select(func.max(Proposal.updated_at))
            .where(Proposal.decision_id == Decision.id)
            .correlate(Decision)
            .scalar_subquery()
        )
        locked_at = (
            select(DecisionLock.locked_at)
            .where(DecisionLock.decision_id == Decision.id)
            .correlate(Decision)
            .scalar_subquery()
        )
        statement = (
            select(Decision.id)
            .outerjoin(
                DecisionSearchDocument,
                DecisionSearchDocument.decision_id == Decision.id,
            )
            .where(
                or_(
                    DecisionSearchDocument.id.is_(None),
                    DecisionSearchDocument.indexed_at < Decision.updated_at,
                    DecisionSearchDocument.indexed_at < latest_proposal,
                    DecisionSearchDocument.indexed_at < locked_at,
                )
            )
            .order_by(Decision.updated_at)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_index_source(
        self, decision_id: UUID
    ) -> tuple[Decision, list[Proposal], DecisionLock | None] | None:
        decision = await self._session.get(Decision, decision_id)
        if decision is None:
            return None
        proposals = list(
            (
                await self._session.scalars(
                    select(Proposal)
                    .where(Proposal.decision_id == decision_id)
                    .order_by(Proposal.created_at)
                )
            ).all()
        )
        decision_lock = cast(
            DecisionLock | None,
            await self._session.scalar(
                select(DecisionLock).where(DecisionLock.decision_id == decision_id)
            ),
        )
        return decision, proposals, decision_lock

    async def upsert(
        self,
        *,
        decision: Decision,
        body: str,
        indexed_at: datetime,
    ) -> None:
        statement = insert(DecisionSearchDocument).values(
            id=func.gen_random_uuid(),
            workspace_id=decision.workspace_id,
            decision_id=decision.id,
            title=decision.title,
            body=body,
            decision_status=decision.status.value,
            category=decision.category.value,
            indexed_at=indexed_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[DecisionSearchDocument.decision_id],
            set_={
                "workspace_id": statement.excluded.workspace_id,
                "title": statement.excluded.title,
                "body": statement.excluded.body,
                "decision_status": statement.excluded.decision_status,
                "category": statement.excluded.category,
                "indexed_at": statement.excluded.indexed_at,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()

    async def search(
        self,
        workspace_id: UUID,
        query: str,
        *,
        status: str | None,
        category: str | None,
        limit: int,
        offset: int,
    ) -> list[SearchResultRecord]:
        tsquery = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(DecisionSearchDocument.search_vector, tsquery)
        headline = func.ts_headline(
            "english",
            DecisionSearchDocument.body,
            tsquery,
            "StartSel=<mark>, StopSel=</mark>, MaxWords=24, MinWords=8",
        )
        statement: Select[tuple[object, ...]] = select(
            DecisionSearchDocument.decision_id,
            DecisionSearchDocument.title,
            DecisionSearchDocument.decision_status,
            DecisionSearchDocument.category,
            headline,
            rank,
            DecisionSearchDocument.indexed_at,
        ).where(
            DecisionSearchDocument.workspace_id == workspace_id,
            DecisionSearchDocument.search_vector.op("@@")(tsquery),
        )
        if status is not None:
            statement = statement.where(DecisionSearchDocument.decision_status == status)
        if category is not None:
            statement = statement.where(DecisionSearchDocument.category == category)
        rows = (
            await self._session.execute(
                statement.order_by(rank.desc(), DecisionSearchDocument.indexed_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [
            SearchResultRecord(
                decision_id=cast(UUID, row[0]),
                title=cast(str, row[1]),
                status=cast(str, row[2]),
                category=cast(str, row[3]),
                headline=cast(str, row[4]),
                rank=float(cast(float, row[5])),
                indexed_at=cast(datetime, row[6]),
            )
            for row in rows
        ]


def utc_now() -> datetime:
    return datetime.now(UTC)
