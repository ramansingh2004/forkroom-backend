from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VoteAlreadyCastError, VotingConflictError
from app.models.voting import (
    Vote,
    VotingEligibleVoter,
    VotingSession,
    VotingSessionProposal,
    VotingSessionStatus,
)


@dataclass(frozen=True, slots=True)
class ProposalVoteTally:
    proposal_id: UUID
    votes: int


class VotingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, voting_session: VotingSession) -> VotingSession:
        self._session.add(voting_session)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise VotingConflictError from error
        await self._session.refresh(voting_session)
        return voting_session

    async def list_for_decision(self, decision_id: UUID) -> list[VotingSession]:
        statement = (
            select(VotingSession)
            .where(VotingSession.decision_id == decision_id)
            .order_by(VotingSession.created_at.desc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_for_decision(
        self,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession | None:
        statement = select(VotingSession).where(
            VotingSession.id == voting_session_id,
            VotingSession.decision_id == decision_id,
        )
        return cast(VotingSession | None, await self._session.scalar(statement))

    async def has_unfinished_for_decision(self, decision_id: UUID) -> bool:
        statement = select(
            select(VotingSession.id)
            .where(
                VotingSession.decision_id == decision_id,
                VotingSession.status.in_(
                    {
                        VotingSessionStatus.DRAFT,
                        VotingSessionStatus.OPEN,
                    }
                ),
            )
            .exists()
        )
        return bool(await self._session.scalar(statement))

    async def open(
        self,
        voting_session: VotingSession,
        *,
        eligible_user_ids: list[UUID],
        proposal_ids: list[UUID],
        opened_at: datetime,
    ) -> VotingSession:
        voting_session.status = VotingSessionStatus.OPEN
        voting_session.opened_at = opened_at
        voting_session.eligible_voter_count = len(eligible_user_ids)
        self._session.add_all(
            [
                VotingEligibleVoter(
                    voting_session_id=voting_session.id,
                    user_id=user_id,
                )
                for user_id in eligible_user_ids
            ]
        )
        self._session.add_all(
            [
                VotingSessionProposal(
                    voting_session_id=voting_session.id,
                    proposal_id=proposal_id,
                )
                for proposal_id in proposal_ids
            ]
        )
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise VotingConflictError from error
        await self._session.refresh(voting_session)
        return voting_session

    async def close(
        self,
        voting_session: VotingSession,
        *,
        closed_at: datetime,
    ) -> VotingSession:
        voting_session.status = VotingSessionStatus.CLOSED
        voting_session.closed_at = closed_at
        await self._session.commit()
        await self._session.refresh(voting_session)
        return voting_session

    async def cancel(
        self,
        voting_session: VotingSession,
        *,
        cancelled_at: datetime,
    ) -> VotingSession:
        voting_session.status = VotingSessionStatus.CANCELLED
        voting_session.cancelled_at = cancelled_at
        await self._session.commit()
        await self._session.refresh(voting_session)
        return voting_session

    async def is_eligible_voter(
        self,
        voting_session_id: UUID,
        user_id: UUID,
    ) -> bool:
        statement = select(
            select(VotingEligibleVoter.id)
            .where(
                VotingEligibleVoter.voting_session_id == voting_session_id,
                VotingEligibleVoter.user_id == user_id,
            )
            .exists()
        )
        return bool(await self._session.scalar(statement))

    async def is_session_proposal(
        self,
        voting_session_id: UUID,
        proposal_id: UUID,
    ) -> bool:
        statement = select(
            select(VotingSessionProposal.id)
            .where(
                VotingSessionProposal.voting_session_id == voting_session_id,
                VotingSessionProposal.proposal_id == proposal_id,
            )
            .exists()
        )
        return bool(await self._session.scalar(statement))

    async def create_vote(self, vote: Vote) -> Vote:
        self._session.add(vote)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise VoteAlreadyCastError from error
        await self._session.refresh(vote)
        return vote

    async def count_votes(self, voting_session_id: UUID) -> int:
        statement = select(func.count(Vote.id)).where(Vote.voting_session_id == voting_session_id)
        return int(await self._session.scalar(statement) or 0)

    async def list_tallies(
        self,
        voting_session_id: UUID,
    ) -> list[ProposalVoteTally]:
        statement = (
            select(
                VotingSessionProposal.proposal_id,
                func.count(Vote.id),
            )
            .outerjoin(
                Vote,
                (Vote.voting_session_id == VotingSessionProposal.voting_session_id)
                & (Vote.proposal_id == VotingSessionProposal.proposal_id),
            )
            .where(VotingSessionProposal.voting_session_id == voting_session_id)
            .group_by(VotingSessionProposal.proposal_id)
            .order_by(VotingSessionProposal.proposal_id)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            ProposalVoteTally(
                proposal_id=row[0],
                votes=int(row[1]),
            )
            for row in rows
        ]
