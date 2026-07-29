from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    DecisionLockAccessDeniedError,
    DecisionLockConflictError,
    DecisionLockInvalidResultError,
    VotingBlockedByObjectionsError,
)
from app.models.decision import Decision, DecisionCategory, DecisionLock, DecisionStatus
from app.models.objection import Objection, ObjectionSeverity, ObjectionStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.decision_lock import DecisionLockCreateRequest
from app.schemas.voting import ProposalVoteTallyResponse, VotingResultResponse
from app.services.decision_lock import DecisionLockService
from app.services.voting import VotingService


@pytest.fixture
def lock_repository() -> AsyncMock:
    return AsyncMock(spec=DecisionLockRepository)


@pytest.fixture
def decision_repository() -> AsyncMock:
    return AsyncMock(spec=DecisionRepository)


@pytest.fixture
def proposal_repository() -> AsyncMock:
    return AsyncMock(spec=ProposalRepository)


@pytest.fixture
def objection_repository() -> AsyncMock:
    return AsyncMock(spec=ObjectionRepository)


@pytest.fixture
def workspace_repository() -> AsyncMock:
    return AsyncMock(spec=WorkspaceRepository)


@pytest.fixture
def voting_service() -> AsyncMock:
    return AsyncMock(spec=VotingService)


@pytest.fixture
def service(
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    proposal_repository: AsyncMock,
    objection_repository: AsyncMock,
    workspace_repository: AsyncMock,
    voting_service: AsyncMock,
) -> DecisionLockService:
    return DecisionLockService(
        lock_repository,
        decision_repository,
        proposal_repository,
        objection_repository,
        workspace_repository,
        voting_service,
    )


def make_context(
    *,
    role: WorkspaceRole = WorkspaceRole.ADMIN,
) -> tuple[User, Workspace, WorkspaceMember, Decision]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="password-hash",
        display_name="Raman Singh",
        is_active=True,
    )
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=uuid4())
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the API framework",
        summary="Choose the long-term backend framework.",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.ACTIVE,
    )
    return user, workspace, membership, decision


def grant_context(
    workspace_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace: Workspace,
    membership: WorkspaceMember,
    decision: Decision,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = membership
    decision_repository.get_for_workspace.return_value = decision


def make_result(
    voting_session_id: object,
    winner: Proposal,
    alternative: Proposal,
    *,
    valid: bool = True,
    tie: bool = False,
) -> VotingResultResponse:
    return VotingResultResponse(
        voting_session_id=voting_session_id,
        eligible_voter_count=5,
        votes_cast=5,
        quorum_percentage=60,
        required_votes=3,
        quorum_met=valid,
        result_valid=valid,
        winner_proposal_id=winner.id if valid and not tie else None,
        is_tie=tie,
        tallies=[
            ProposalVoteTallyResponse(
                proposal_id=winner.id,
                votes=3,
                percentage=60.0,
            ),
            ProposalVoteTallyResponse(
                proposal_id=alternative.id,
                votes=2,
                percentage=40.0,
            ),
        ],
    )


async def test_admin_locks_valid_winning_result(
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    proposal_repository: AsyncMock,
    objection_repository: AsyncMock,
    workspace_repository: AsyncMock,
    voting_service: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    winner = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        title="Use FastAPI",
        content="Adopt FastAPI for the backend.",
        status=ProposalStatus.SUBMITTED,
    )
    alternative = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        title="Use Django",
        content="Adopt Django for the backend.",
        status=ProposalStatus.SUBMITTED,
    )
    objection = Objection(
        id=uuid4(),
        proposal_id=winner.id,
        created_by_id=uuid4(),
        severity=ObjectionSeverity.MAJOR,
        status=ObjectionStatus.RESOLVED,
        title="Async ecosystem maturity",
        description="Confirm every dependency supports async.",
        resolution_note="Dependencies were verified.",
        resolved_by_id=user.id,
        resolved_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    voting_session_id = uuid4()
    result = make_result(voting_session_id, winner, alternative)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    lock_repository.get_for_decision.return_value = None
    objection_repository.has_open_blocking_for_decision.return_value = False
    voting_service.get_result.return_value = result
    proposal_repository.get_for_decision.side_effect = [winner, alternative]
    objection_repository.list_for_proposal.side_effect = [[objection], []]
    lock_repository.create.side_effect = lambda decision_lock, _decision, **_: decision_lock

    decision_lock = await service.create(
        user,
        workspace.id,
        decision.id,
        DecisionLockCreateRequest(voting_session_id=voting_session_id),
    )

    assert decision_lock.winning_proposal_id == winner.id
    assert len(decision_lock.document_hash) == 64
    assert service.hash_snapshot(decision_lock.snapshot) == decision_lock.document_hash
    assert decision_lock.snapshot["approved_proposal"]["title"] == "Use FastAPI"
    dissent = decision_lock.snapshot["dissent"]
    assert dissent["alternative_proposals"][0]["proposal"]["title"] == "Use Django"
    assert dissent["objections_to_approved_proposal"][0]["status"] == "resolved"
    lock_repository.create.assert_awaited_once()


async def test_member_cannot_lock_decision(
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(role=WorkspaceRole.MEMBER)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )

    with pytest.raises(DecisionLockAccessDeniedError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            DecisionLockCreateRequest(voting_session_id=uuid4()),
        )

    lock_repository.create.assert_not_awaited()


async def test_existing_lock_is_rejected(
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    lock_repository.get_for_decision.return_value = DecisionLock(decision_id=decision.id)

    with pytest.raises(DecisionLockConflictError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            DecisionLockCreateRequest(voting_session_id=uuid4()),
        )


async def test_new_blocking_objection_prevents_lock(
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    objection_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    lock_repository.get_for_decision.return_value = None
    objection_repository.has_open_blocking_for_decision.return_value = True

    with pytest.raises(VotingBlockedByObjectionsError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            DecisionLockCreateRequest(voting_session_id=uuid4()),
        )


@pytest.mark.parametrize(
    ("valid", "tie"),
    [
        (False, False),
        (True, True),
    ],
)
async def test_invalid_or_tied_result_cannot_be_locked(
    valid: bool,
    tie: bool,
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    proposal_repository: AsyncMock,
    objection_repository: AsyncMock,
    workspace_repository: AsyncMock,
    voting_service: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    winner = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        title="Use FastAPI",
        status=ProposalStatus.SUBMITTED,
    )
    alternative = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        title="Use Django",
        status=ProposalStatus.SUBMITTED,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    lock_repository.get_for_decision.return_value = None
    objection_repository.has_open_blocking_for_decision.return_value = False
    voting_service.get_result.return_value = make_result(
        uuid4(),
        winner,
        alternative,
        valid=valid,
        tie=tie,
    )

    with pytest.raises(DecisionLockInvalidResultError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            DecisionLockCreateRequest(voting_session_id=uuid4()),
        )

    proposal_repository.get_for_decision.assert_not_awaited()


async def test_verify_detects_snapshot_tampering(
    service: DecisionLockService,
    lock_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    snapshot: dict[str, object] = {"approved_proposal": {"title": "Use FastAPI"}}
    decision_lock = DecisionLock(
        id=uuid4(),
        decision_id=decision.id,
        voting_session_id=uuid4(),
        winning_proposal_id=uuid4(),
        locked_by_id=user.id,
        snapshot_version=1,
        snapshot=snapshot,
        document_hash=service.hash_snapshot(snapshot),
        locked_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    decision_lock.snapshot = {"approved_proposal": {"title": "Use Django"}}
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    lock_repository.get_for_decision.return_value = decision_lock

    verification = await service.verify(user, workspace.id, decision.id)

    assert verification.valid is False
    assert verification.computed_hash != verification.document_hash
