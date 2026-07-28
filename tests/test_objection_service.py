from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    ObjectionAccessDeniedError,
    ObjectionImmutableError,
    ObjectionInvalidTransitionError,
    ProposalImmutableError,
)
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.objection import Objection, ObjectionSeverity, ObjectionStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.objection import (
    ObjectionCreateRequest,
    ObjectionTransitionRequest,
    ObjectionUpdateRequest,
)
from app.services.objection import ObjectionService


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
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> ObjectionService:
    return ObjectionService(
        objection_repository,
        proposal_repository,
        decision_repository,
        workspace_repository,
    )


def make_user(email: str = "raman@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        password_hash="password-hash",
        display_name="Raman Singh",
        is_active=True,
    )


def make_context(
    user: User,
    *,
    role: WorkspaceRole = WorkspaceRole.MEMBER,
    proposal_status: ProposalStatus = ProposalStatus.SUBMITTED,
) -> tuple[Workspace, Decision, Proposal, WorkspaceMember]:
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=uuid4())
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.ACTIVE,
    )
    proposal = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        title="Use FastAPI",
        status=proposal_status,
    )
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    return workspace, decision, proposal, membership


def grant_context(
    workspace_repository: AsyncMock,
    decision_repository: AsyncMock,
    proposal_repository: AsyncMock,
    workspace: Workspace,
    decision: Decision,
    proposal: Proposal,
    membership: WorkspaceMember,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = membership
    decision_repository.get_for_workspace.return_value = decision
    proposal_repository.get_for_decision.return_value = proposal


def make_objection(
    proposal: Proposal,
    user: User,
    *,
    status: ObjectionStatus = ObjectionStatus.OPEN,
) -> Objection:
    return Objection(
        id=uuid4(),
        proposal_id=proposal.id,
        created_by_id=user.id,
        severity=ObjectionSeverity.BLOCKING,
        status=status,
        title="Migration safety is unclear",
        description="The proposal does not explain rollback behavior.",
    )


async def test_member_can_raise_blocking_objection_on_submitted_proposal(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.create.side_effect = lambda objection: objection

    objection = await service.create(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        ObjectionCreateRequest(
            severity=ObjectionSeverity.BLOCKING,
            title="Migration safety is unclear",
            description="The proposal does not explain rollback behavior.",
        ),
    )

    assert objection.status is ObjectionStatus.OPEN
    assert objection.severity is ObjectionSeverity.BLOCKING
    objection_repository.create.assert_awaited_once_with(objection)


async def test_objection_requires_submitted_proposal(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(
        user,
        proposal_status=ProposalStatus.DRAFT,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )

    with pytest.raises(ProposalImmutableError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            ObjectionCreateRequest(
                severity=ObjectionSeverity.MAJOR,
                title="Incomplete evidence",
                description="The proposal needs benchmark evidence.",
            ),
        )

    objection_repository.create.assert_not_awaited()


async def test_viewer_cannot_raise_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(
        user,
        role=WorkspaceRole.VIEWER,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )

    with pytest.raises(ObjectionAccessDeniedError):
        await service.create(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            ObjectionCreateRequest(
                severity=ObjectionSeverity.INFORMATIONAL,
                title="Documentation note",
                description="The proposal could link the framework documentation.",
            ),
        )

    objection_repository.create.assert_not_awaited()


async def test_author_can_update_open_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection
    objection_repository.update.side_effect = lambda objection, **_: objection

    result = await service.update(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        objection.id,
        ObjectionUpdateRequest(severity=ObjectionSeverity.MAJOR),
    )

    assert result is objection
    objection_repository.update.assert_awaited_once_with(
        objection,
        values={"severity": ObjectionSeverity.MAJOR},
    )


async def test_resolved_objection_cannot_be_edited(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user, status=ObjectionStatus.RESOLVED)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection

    with pytest.raises(ObjectionImmutableError):
        await service.update(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            objection.id,
            ObjectionUpdateRequest(title="Changed concern"),
        )


async def test_author_can_resolve_own_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection
    objection_repository.transition.side_effect = lambda objection, **_: objection

    await service.transition(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        objection.id,
        ObjectionTransitionRequest(
            status=ObjectionStatus.RESOLVED,
            note="The rollback section now addresses this concern.",
        ),
    )

    call = objection_repository.transition.await_args
    assert call.kwargs["status"] is ObjectionStatus.RESOLVED
    assert call.kwargs["actor_id"] == user.id
    assert isinstance(call.kwargs["resolved_at"], datetime)


async def test_member_cannot_dismiss_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection

    with pytest.raises(ObjectionAccessDeniedError):
        await service.transition(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            objection.id,
            ObjectionTransitionRequest(
                status=ObjectionStatus.DISMISSED,
                note="This concern does not apply.",
            ),
        )


async def test_admin_can_dismiss_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    admin = make_user()
    author = make_user("member@example.com")
    workspace, decision, proposal, membership = make_context(
        admin,
        role=WorkspaceRole.ADMIN,
    )
    objection = make_objection(proposal, author)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection
    objection_repository.transition.side_effect = lambda objection, **_: objection

    await service.transition(
        admin,
        workspace.id,
        decision.id,
        proposal.id,
        objection.id,
        ObjectionTransitionRequest(
            status=ObjectionStatus.DISMISSED,
            note="This duplicates another tracked concern.",
        ),
    )

    assert objection_repository.transition.await_args.kwargs["status"] is (
        ObjectionStatus.DISMISSED
    )


async def test_author_can_reopen_resolved_objection(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user, status=ObjectionStatus.RESOLVED)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection
    objection_repository.transition.side_effect = lambda objection, **_: objection

    await service.transition(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        objection.id,
        ObjectionTransitionRequest(
            status=ObjectionStatus.OPEN,
            note="The latest proposal revision reintroduces the risk.",
        ),
    )

    call = objection_repository.transition.await_args
    assert call.kwargs["status"] is ObjectionStatus.OPEN
    assert call.kwargs["resolved_at"] is None


async def test_same_status_transition_is_rejected(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection

    with pytest.raises(ObjectionInvalidTransitionError):
        await service.transition(
            user,
            workspace.id,
            decision.id,
            proposal.id,
            objection.id,
            ObjectionTransitionRequest(
                status=ObjectionStatus.OPEN,
                note="Keep this concern open.",
            ),
        )


async def test_history_requires_visible_parent_context(
    service: ObjectionService,
    objection_repository: AsyncMock,
    proposal_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace, decision, proposal, membership = make_context(user)
    objection = make_objection(proposal, user)
    grant_context(
        workspace_repository,
        decision_repository,
        proposal_repository,
        workspace,
        decision,
        proposal,
        membership,
    )
    objection_repository.get_for_proposal.return_value = objection
    objection_repository.list_status_events.return_value = []

    events = await service.list_history(
        user,
        workspace.id,
        decision.id,
        proposal.id,
        objection.id,
    )

    assert events == []
    objection_repository.list_status_events.assert_awaited_once_with(objection.id)
