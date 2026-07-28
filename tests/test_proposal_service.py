from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    CriterionAccessDeniedError,
    CriterionConflictError,
    ProposalAccessDeniedError,
    ProposalImmutableError,
)
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.proposal import (
    DecisionCriterion,
    Proposal,
    ProposalScore,
    ProposalStatus,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.proposal import (
    CriterionCreateRequest,
    CriterionReorderRequest,
    ProposalCreateRequest,
    ProposalScoreUpsertRequest,
    ProposalTransitionRequest,
    ProposalUpdateRequest,
)
from app.services.proposal import ProposalService


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
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> ProposalService:
    return ProposalService(
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


def make_workspace() -> Workspace:
    return Workspace(
        id=uuid4(),
        name="Backend Guild",
        owner_id=uuid4(),
    )


def make_decision(
    workspace: Workspace,
    user: User,
    *,
    status: DecisionStatus = DecisionStatus.ACTIVE,
) -> Decision:
    return Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=status,
    )


def make_proposal(
    decision: Decision,
    user: User,
    *,
    status: ProposalStatus = ProposalStatus.DRAFT,
) -> Proposal:
    return Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        title="Use FastAPI",
        status=status,
    )


def grant_context(
    workspace_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace: Workspace,
    decision: Decision,
    user: User,
    role: WorkspaceRole,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    decision_repository.get_for_workspace.return_value = decision


async def test_member_can_create_proposal_branch(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )
    proposal_repository.create.side_effect = lambda proposal: proposal

    proposal = await service.create(
        user,
        workspace.id,
        decision.id,
        ProposalCreateRequest(title="Use FastAPI"),
    )

    assert proposal.status is ProposalStatus.DRAFT
    assert proposal.created_by_id == user.id
    proposal_repository.create.assert_awaited_once_with(proposal)


async def test_viewer_cannot_create_proposal(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.VIEWER,
    )

    with pytest.raises(ProposalAccessDeniedError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            ProposalCreateRequest(title="Use FastAPI"),
        )

    proposal_repository.create.assert_not_awaited()


async def test_member_cannot_edit_another_authors_proposal(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    other_user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    proposal = make_proposal(decision, other_user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )
    proposal_repository.get_for_decision.return_value = proposal

    with pytest.raises(ProposalAccessDeniedError):
        await service.update(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            ProposalUpdateRequest(title="Edited proposal"),
        )

    proposal_repository.update.assert_not_awaited()


async def test_submitted_proposal_must_be_reopened_before_editing(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    proposal = make_proposal(decision, user, status=ProposalStatus.SUBMITTED)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )
    proposal_repository.get_for_decision.return_value = proposal

    with pytest.raises(ProposalImmutableError):
        await service.update(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            ProposalUpdateRequest(title="Edited proposal"),
        )


async def test_author_can_submit_draft_proposal(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    proposal = make_proposal(decision, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )
    proposal_repository.get_for_decision.return_value = proposal
    proposal_repository.update.side_effect = lambda item, **values: item

    await service.transition(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        ProposalTransitionRequest(status="submitted"),
    )

    values = proposal_repository.update.await_args.kwargs["values"]
    assert values["status"] is ProposalStatus.SUBMITTED
    assert isinstance(values["submitted_at"], datetime)
    assert values["withdrawn_at"] is None


async def test_only_admin_or_owner_can_create_criteria(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )

    with pytest.raises(CriterionAccessDeniedError):
        await service.create_criterion(
            user,
            workspace.id,
            decision.id,
            CriterionCreateRequest(name="Operational complexity"),
        )

    proposal_repository.create_criterion.assert_not_awaited()


async def test_admin_appends_weighted_criterion(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.ADMIN,
    )
    proposal_repository.next_criterion_position.return_value = 2
    proposal_repository.create_criterion.side_effect = lambda criterion: criterion

    criterion = await service.create_criterion(
        user,
        workspace.id,
        decision.id,
        CriterionCreateRequest(
            name="Operational complexity",
            weight=3,
        ),
    )

    assert criterion.position == 2
    assert criterion.weight == 3


async def test_reorder_requires_every_criterion_exactly_once(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.OWNER,
    )
    criterion = DecisionCriterion(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        name="Cost",
        weight=2,
        position=0,
    )
    proposal_repository.list_criteria.return_value = [criterion]

    with pytest.raises(CriterionConflictError):
        await service.reorder_criteria(
            user,
            workspace.id,
            decision.id,
            CriterionReorderRequest(criterion_ids=[uuid4()]),
        )

    proposal_repository.reorder_criteria.assert_not_awaited()


async def test_only_submitted_proposals_can_be_scored(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    proposal = make_proposal(decision, user)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.MEMBER,
    )
    proposal_repository.get_for_decision.return_value = proposal

    with pytest.raises(ProposalImmutableError):
        await service.upsert_score(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            uuid4(),
            ProposalScoreUpsertRequest(score=5),
        )

    proposal_repository.upsert_score.assert_not_awaited()


async def test_comparison_calculates_complete_weighted_score(
    service: ProposalService,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    proposal = make_proposal(decision, user, status=ProposalStatus.SUBMITTED)
    now = datetime(2026, 7, 28, tzinfo=UTC)
    proposal.created_at = now
    proposal.updated_at = now
    first = DecisionCriterion(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        name="Cost",
        weight=1,
        position=0,
        created_at=now,
        updated_at=now,
    )
    second = DecisionCriterion(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        name="Reliability",
        weight=3,
        position=1,
        created_at=now,
        updated_at=now,
    )
    scores = [
        ProposalScore(
            id=uuid4(),
            proposal_id=proposal.id,
            criterion_id=first.id,
            scored_by_id=user.id,
            score=2,
            created_at=now,
            updated_at=now,
        ),
        ProposalScore(
            id=uuid4(),
            proposal_id=proposal.id,
            criterion_id=second.id,
            scored_by_id=user.id,
            score=4,
            created_at=now,
            updated_at=now,
        ),
    ]
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        decision,
        user,
        WorkspaceRole.VIEWER,
    )
    proposal_repository.list_for_decision.return_value = [proposal]
    proposal_repository.list_criteria.return_value = [first, second]
    proposal_repository.list_scores_for_decision.return_value = scores

    result = await service.compare(user, workspace.id, decision.id)

    assert len(result) == 1
    assert result[0].weighted_score == 3.5
    assert len(result[0].scores) == 2
