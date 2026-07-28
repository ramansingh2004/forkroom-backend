from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionNotFoundError,
    ProposalNotFoundError,
    VotingAccessDeniedError,
    VotingBlockedByObjectionsError,
    VotingClosedError,
    VotingConflictError,
    VotingInvalidTransitionError,
    VotingResultUnavailableError,
    VotingSessionNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionStatus
from app.models.proposal import ProposalStatus
from app.models.user import User
from app.models.voting import Vote, VotingSession, VotingSessionStatus
from app.models.workspace import WorkspaceMember
from app.permissions.voting import can_manage_voting
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.voting import VotingRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.voting import (
    ProposalVoteTallyResponse,
    VoteCastRequest,
    VotingResultResponse,
    VotingSessionCreateRequest,
)


class VotingService:
    def __init__(
        self,
        voting_repository: VotingRepository,
        objection_repository: ObjectionRepository,
        proposal_repository: ProposalRepository,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._voting = voting_repository
        self._objections = objection_repository
        self._proposals = proposal_repository
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def create_session(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: VotingSessionCreateRequest,
    ) -> VotingSession:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_active_decision(decision)
        if not can_manage_voting(membership.role):
            raise VotingAccessDeniedError
        if await self._voting.has_unfinished_for_decision(decision_id):
            raise VotingConflictError
        return await self._voting.create(
            VotingSession(
                decision_id=decision_id,
                created_by_id=current_user.id,
                status=VotingSessionStatus.DRAFT,
                quorum_percentage=payload.quorum_percentage,
                closes_at=payload.closes_at,
            )
        )

    async def list_sessions(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> list[VotingSession]:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._voting.list_for_decision(decision_id)

    async def get_session(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._require_session(decision_id, voting_session_id)

    async def open_session(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_active_decision(decision)
        if not can_manage_voting(membership.role):
            raise VotingAccessDeniedError
        voting_session = await self._require_session(decision_id, voting_session_id)
        if voting_session.status is not VotingSessionStatus.DRAFT:
            raise VotingInvalidTransitionError

        now = datetime.now(UTC)
        if voting_session.closes_at is not None and voting_session.closes_at <= now:
            raise VotingClosedError
        if await self._objections.has_open_blocking_for_decision(decision_id):
            raise VotingBlockedByObjectionsError

        proposals = await self._proposals.list_for_decision(
            decision_id,
            status=ProposalStatus.SUBMITTED,
        )
        if len(proposals) < 2:
            raise VotingConflictError
        eligible_user_ids = await self._workspaces.list_voting_eligible_user_ids(workspace_id)
        if not eligible_user_ids:
            raise VotingConflictError

        return await self._voting.open(
            voting_session,
            eligible_user_ids=eligible_user_ids,
            proposal_ids=[proposal.id for proposal in proposals],
            opened_at=now,
        )

    async def cast_vote(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
        payload: VoteCastRequest,
    ) -> Vote:
        await self._context(current_user.id, workspace_id, decision_id)
        voting_session = await self._require_session(decision_id, voting_session_id)
        if voting_session.status is not VotingSessionStatus.OPEN:
            raise VotingClosedError
        if voting_session.closes_at is not None and voting_session.closes_at <= datetime.now(UTC):
            raise VotingClosedError
        if not await self._voting.is_eligible_voter(voting_session.id, current_user.id):
            raise VotingAccessDeniedError
        if not await self._voting.is_session_proposal(
            voting_session.id,
            payload.proposal_id,
        ):
            raise ProposalNotFoundError
        return await self._voting.create_vote(
            Vote(
                voting_session_id=voting_session.id,
                voter_id=current_user.id,
                proposal_id=payload.proposal_id,
            )
        )

    async def close_session(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession:
        membership, _ = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_voting(membership.role):
            raise VotingAccessDeniedError
        voting_session = await self._require_session(decision_id, voting_session_id)
        if voting_session.status is not VotingSessionStatus.OPEN:
            raise VotingInvalidTransitionError
        return await self._voting.close(
            voting_session,
            closed_at=datetime.now(UTC),
        )

    async def cancel_session(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession:
        membership, _ = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_voting(membership.role):
            raise VotingAccessDeniedError
        voting_session = await self._require_session(decision_id, voting_session_id)
        if voting_session.status not in {
            VotingSessionStatus.DRAFT,
            VotingSessionStatus.OPEN,
        }:
            raise VotingInvalidTransitionError
        return await self._voting.cancel(
            voting_session,
            cancelled_at=datetime.now(UTC),
        )

    async def get_result(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingResultResponse:
        await self._context(current_user.id, workspace_id, decision_id)
        voting_session = await self._require_session(decision_id, voting_session_id)
        if voting_session.status is not VotingSessionStatus.CLOSED:
            raise VotingResultUnavailableError

        votes_cast = await self._voting.count_votes(voting_session.id)
        required_votes = ceil(
            voting_session.eligible_voter_count * voting_session.quorum_percentage / 100
        )
        quorum_met = votes_cast >= required_votes
        stored_tallies = await self._voting.list_tallies(voting_session.id)
        tallies = [
            ProposalVoteTallyResponse(
                proposal_id=tally.proposal_id,
                votes=tally.votes,
                percentage=round(
                    tally.votes * 100 / votes_cast,
                    2,
                )
                if votes_cast
                else 0.0,
            )
            for tally in stored_tallies
        ]

        winner_proposal_id: UUID | None = None
        is_tie = False
        if quorum_met and tallies:
            highest_votes = max(tally.votes for tally in tallies)
            leaders = [tally.proposal_id for tally in tallies if tally.votes == highest_votes]
            is_tie = len(leaders) > 1
            if not is_tie:
                winner_proposal_id = leaders[0]

        return VotingResultResponse(
            voting_session_id=voting_session.id,
            eligible_voter_count=voting_session.eligible_voter_count,
            votes_cast=votes_cast,
            quorum_percentage=voting_session.quorum_percentage,
            required_votes=required_votes,
            quorum_met=quorum_met,
            result_valid=quorum_met,
            winner_proposal_id=winner_proposal_id,
            is_tie=is_tie,
            tallies=tallies,
        )

    async def _context(
        self,
        user_id: UUID,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> tuple[WorkspaceMember, Decision]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        return membership, decision

    @staticmethod
    def _require_active_decision(decision: Decision) -> None:
        if decision.status is not DecisionStatus.ACTIVE:
            raise DecisionImmutableError

    async def _require_session(
        self,
        decision_id: UUID,
        voting_session_id: UUID,
    ) -> VotingSession:
        voting_session = await self._voting.get_for_decision(
            decision_id,
            voting_session_id,
        )
        if voting_session is None:
            raise VotingSessionNotFoundError
        return voting_session
