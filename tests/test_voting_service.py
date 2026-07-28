from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    VotingAccessDeniedError,
    VotingBlockedByObjectionsError,
    VotingClosedError,
    VotingConflictError,
    VotingResultUnavailableError,
)
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.voting import VotingSession, VotingSessionStatus
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.voting import ProposalVoteTally, VotingRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.voting import VoteCastRequest, VotingSessionCreateRequest
from app.services.voting import VotingService


@pytest.fixture
def voting_repository() -> AsyncMock:
    return AsyncMock(spec=VotingRepository)


@pytest.fixture
def objection_repository() -> AsyncMock:
    return AsyncMock(spec=ObjectionRepository)


@pytest.fixture
def proposal_repository() -> AsyncMock:
    return AsyncMock(spec=ProposalRepository)


@pytest.fixture
def decision_repository() -> AsyncMock:
    return AsyncMock(spec=DecisionRepository)


@pytest.fixture
def workspace_repository() -> AsyncMock:
    return AsyncMock(spec=WorkspaceRepository)


@pytest.fixture
def service(
    voting_repository: AsyncMock,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> VotingService:
    return VotingService(
        voting_repository,
        objection_repository,
        proposal_repository,
        decision_repository,
        workspace_repository,
    )


def make_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="password-hash",
        display_name="Raman Singh",
        is_active=True,
    )


def make_context(
    user: User,
    *,
    role: WorkspaceRole = WorkspaceRole.ADMIN,
) -> tuple[Workspace, Decision, WorkspaceMember]:
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=uuid4())
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.ACTIVE,
    )
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    return workspace, decision, membership


def grant_context(
    workspace_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace: Workspace,
    decision: Decision,
    membership: WorkspaceMember,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = membership
    decision_repository.get_for_workspace.return_value = decision


def make_session(
    decision: Decision,
    user: User,
    *,
    status: VotingSessionStatus = VotingSessionStatus.DRAFT,
    eligible_voter_count: int = 0,
    quorum_percentage: int = 60,
    closes_at: datetime | None = None,
) -> VotingSession:
    return VotingSession(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        status=status,
        quorum_percentage=quorum_percentage,
        eligible_voter_count=eligible_voter_count,
        closes_at=closes_at,
    )


def make_proposal(decision: Decision, title: str) -> Proposal:
    return Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        title=title,
        status=ProposalStatus.SUBMITTED,
    )


async def test_admin_creates_draft_voting_session(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.has_unfinished_for_decision.return_value = False
    voting_repository.create.side_effect = lambda voting_session: voting_session

    voting_session = await service.create_session(
        user,
        workspace.id,
        decision.id,
        VotingSessionCreateRequest(quorum_percentage=70),
    )

    assert voting_session.status is VotingSessionStatus.DRAFT
    assert voting_session.quorum_percentage == 70
    voting_repository.create.assert_awaited_once_with(voting_session)


async def test_member_cannot_create_voting_session(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.MEMBER)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )

    with pytest.raises(VotingAccessDeniedError):
        await service.create_session(
            user,
            workspace.id,
            decision.id,
            VotingSessionCreateRequest(),
        )

    voting_repository.create.assert_not_awaited()


async def test_only_one_unfinished_session_is_allowed(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.has_unfinished_for_decision.return_value = True

    with pytest.raises(VotingConflictError):
        await service.create_session(
            user,
            workspace.id,
            decision.id,
            VotingSessionCreateRequest(),
        )


async def test_blocking_objection_prevents_opening(
    service: VotingService,
    voting_repository: AsyncMock,
    objection_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    voting_session = make_session(decision, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    objection_repository.has_open_blocking_for_decision.return_value = True

    with pytest.raises(VotingBlockedByObjectionsError):
        await service.open_session(
            user,
            workspace.id,
            decision.id,
            voting_session.id,
        )

    voting_repository.open.assert_not_awaited()


async def test_open_snapshots_eligible_voters_and_submitted_proposals(
    service: VotingService,
    voting_repository: AsyncMock,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    voting_session = make_session(decision, user)
    proposals = [
        make_proposal(decision, "Use FastAPI"),
        make_proposal(decision, "Use Django"),
    ]
    voter_ids = [user.id, uuid4(), uuid4()]
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    objection_repository.has_open_blocking_for_decision.return_value = False
    proposal_repository.list_for_decision.return_value = proposals
    workspace_repository.list_voting_eligible_user_ids.return_value = voter_ids
    voting_repository.open.side_effect = lambda voting_session, **_: voting_session

    result = await service.open_session(
        user,
        workspace.id,
        decision.id,
        voting_session.id,
    )

    assert result is voting_session
    assert voting_repository.open.await_args.kwargs["eligible_user_ids"] == voter_ids
    assert voting_repository.open.await_args.kwargs["proposal_ids"] == [
        proposal.id for proposal in proposals
    ]


async def test_open_requires_two_submitted_proposals(
    service: VotingService,
    voting_repository: AsyncMock,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    voting_session = make_session(decision, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    objection_repository.has_open_blocking_for_decision.return_value = False
    proposal_repository.list_for_decision.return_value = [make_proposal(decision, "Use FastAPI")]

    with pytest.raises(VotingConflictError):
        await service.open_session(
            user,
            workspace.id,
            decision.id,
            voting_session.id,
        )


async def test_eligible_participant_casts_one_ballot(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.MEMBER)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.OPEN,
        eligible_voter_count=3,
    )
    proposal = make_proposal(decision, "Use FastAPI")
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    voting_repository.is_eligible_voter.return_value = True
    voting_repository.is_session_proposal.return_value = True
    voting_repository.create_vote.side_effect = lambda vote: vote

    vote = await service.cast_vote(
        user,
        workspace.id,
        decision.id,
        voting_session.id,
        VoteCastRequest(proposal_id=proposal.id),
    )

    assert vote.voter_id == user.id
    assert vote.proposal_id == proposal.id
    voting_repository.create_vote.assert_awaited_once_with(vote)


async def test_noneligible_participant_cannot_vote(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.VIEWER)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.OPEN,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    voting_repository.is_eligible_voter.return_value = False

    with pytest.raises(VotingAccessDeniedError):
        await service.cast_vote(
            user,
            workspace.id,
            decision.id,
            voting_session.id,
            VoteCastRequest(proposal_id=uuid4()),
        )


async def test_expired_voting_window_rejects_ballot(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.MEMBER)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.OPEN,
        closes_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session

    with pytest.raises(VotingClosedError):
        await service.cast_vote(
            user,
            workspace.id,
            decision.id,
            voting_session.id,
            VoteCastRequest(proposal_id=uuid4()),
        )


async def test_closed_result_calculates_quorum_and_winner(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.MEMBER)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.CLOSED,
        eligible_voter_count=5,
        quorum_percentage=60,
    )
    first_proposal_id = uuid4()
    second_proposal_id = uuid4()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    voting_repository.count_votes.return_value = 4
    voting_repository.list_tallies.return_value = [
        ProposalVoteTally(first_proposal_id, 3),
        ProposalVoteTally(second_proposal_id, 1),
    ]

    result = await service.get_result(
        user,
        workspace.id,
        decision.id,
        voting_session.id,
    )

    assert result.required_votes == 3
    assert result.quorum_met is True
    assert result.result_valid is True
    assert result.winner_proposal_id == first_proposal_id
    assert result.tallies[0].percentage == 75.0


async def test_result_without_quorum_has_no_winner(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user, role=WorkspaceRole.MEMBER)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.CLOSED,
        eligible_voter_count=5,
        quorum_percentage=80,
    )
    proposal_id = uuid4()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session
    voting_repository.count_votes.return_value = 3
    voting_repository.list_tallies.return_value = [
        ProposalVoteTally(proposal_id, 3),
    ]

    result = await service.get_result(
        user,
        workspace.id,
        decision.id,
        voting_session.id,
    )

    assert result.required_votes == 4
    assert result.result_valid is False
    assert result.winner_proposal_id is None


async def test_open_session_does_not_expose_results(
    service: VotingService,
    voting_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, membership = make_context(user)
    voting_session = make_session(
        decision,
        user,
        status=VotingSessionStatus.OPEN,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        membership,
    )
    voting_repository.get_for_decision.return_value = voting_session

    with pytest.raises(VotingResultUnavailableError):
        await service.get_result(
            user,
            workspace.id,
            decision.id,
            voting_session.id,
        )
