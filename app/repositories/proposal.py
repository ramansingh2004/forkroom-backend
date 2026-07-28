from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proposal import (
    DecisionCriterion,
    Proposal,
    ProposalScore,
    ProposalStatus,
)


class ProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, proposal: Proposal) -> Proposal:
        self._session.add(proposal)
        await self._session.commit()
        await self._session.refresh(proposal)
        return proposal

    async def list_for_decision(
        self,
        decision_id: UUID,
        *,
        status: ProposalStatus | None,
    ) -> list[Proposal]:
        statement = select(Proposal).where(Proposal.decision_id == decision_id)
        if status is not None:
            statement = statement.where(Proposal.status == status)
        statement = statement.order_by(Proposal.updated_at.desc())
        return list((await self._session.scalars(statement)).all())

    async def get_for_decision(
        self,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> Proposal | None:
        statement = select(Proposal).where(
            Proposal.id == proposal_id,
            Proposal.decision_id == decision_id,
        )
        return cast(Proposal | None, await self._session.scalar(statement))

    async def update(
        self,
        proposal: Proposal,
        *,
        values: dict[str, object],
    ) -> Proposal:
        for field, value in values.items():
            setattr(proposal, field, value)
        await self._session.commit()
        await self._session.refresh(proposal)
        return proposal

    async def delete(self, proposal: Proposal) -> None:
        await self._session.delete(proposal)
        await self._session.commit()

    async def create_criterion(
        self,
        criterion: DecisionCriterion,
    ) -> DecisionCriterion:
        self._session.add(criterion)
        await self._session.commit()
        await self._session.refresh(criterion)
        return criterion

    async def next_criterion_position(self, decision_id: UUID) -> int:
        statement = select(func.coalesce(func.max(DecisionCriterion.position), -1) + 1).where(
            DecisionCriterion.decision_id == decision_id
        )
        return int(await self._session.scalar(statement) or 0)

    async def list_criteria(self, decision_id: UUID) -> list[DecisionCriterion]:
        statement = (
            select(DecisionCriterion)
            .where(DecisionCriterion.decision_id == decision_id)
            .order_by(DecisionCriterion.position.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_criterion(
        self,
        decision_id: UUID,
        criterion_id: UUID,
    ) -> DecisionCriterion | None:
        statement = select(DecisionCriterion).where(
            DecisionCriterion.id == criterion_id,
            DecisionCriterion.decision_id == decision_id,
        )
        return cast(DecisionCriterion | None, await self._session.scalar(statement))

    async def update_criterion(
        self,
        criterion: DecisionCriterion,
        *,
        values: dict[str, object],
    ) -> DecisionCriterion:
        for field, value in values.items():
            setattr(criterion, field, value)
        await self._session.commit()
        await self._session.refresh(criterion)
        return criterion

    async def reorder_criteria(
        self,
        criteria: Sequence[DecisionCriterion],
    ) -> list[DecisionCriterion]:
        for position, criterion in enumerate(criteria):
            criterion.position = position
        await self._session.commit()
        for criterion in criteria:
            await self._session.refresh(criterion)
        return list(criteria)

    async def delete_criterion(self, criterion: DecisionCriterion) -> None:
        await self._session.delete(criterion)
        await self._session.commit()

    async def get_score(
        self,
        proposal_id: UUID,
        criterion_id: UUID,
    ) -> ProposalScore | None:
        statement = select(ProposalScore).where(
            ProposalScore.proposal_id == proposal_id,
            ProposalScore.criterion_id == criterion_id,
        )
        return cast(ProposalScore | None, await self._session.scalar(statement))

    async def upsert_score(
        self,
        score: ProposalScore,
        *,
        score_value: int,
        rationale: str | None,
        scored_by_id: UUID,
    ) -> ProposalScore:
        score.score = score_value
        score.rationale = rationale
        score.scored_by_id = scored_by_id
        self._session.add(score)
        await self._session.commit()
        await self._session.refresh(score)
        return score

    async def list_scores_for_decision(
        self,
        decision_id: UUID,
    ) -> list[ProposalScore]:
        statement = (
            select(ProposalScore)
            .join(Proposal, Proposal.id == ProposalScore.proposal_id)
            .where(Proposal.decision_id == decision_id)
            .order_by(ProposalScore.proposal_id, ProposalScore.criterion_id)
        )
        return list((await self._session.scalars(statement)).all())
