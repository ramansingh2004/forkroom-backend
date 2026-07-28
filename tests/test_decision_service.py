from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    DecisionAccessDeniedError,
    DecisionImmutableError,
    DecisionInvalidTransitionError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.decision import (
    DecisionCreateRequest,
    DecisionTransitionRequest,
    DecisionUpdateRequest,
)
from app.services.decision import DecisionService


@pytest.fixture
def decision_repository() -> AsyncMock:
    return AsyncMock(spec=DecisionRepository)


@pytest.fixture
def workspace_repository() -> AsyncMock:
    return AsyncMock(spec=WorkspaceRepository)


@pytest.fixture
def service(
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> DecisionService:
    return DecisionService(decision_repository, workspace_repository)


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


def make_membership(
    workspace: Workspace,
    user: User,
    role: WorkspaceRole,
) -> WorkspaceMember:
    return WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )


def make_decision(
    workspace: Workspace,
    user: User,
    status: DecisionStatus = DecisionStatus.DRAFT,
) -> Decision:
    return Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=status,
    )


def grant_role(
    workspace_repository: AsyncMock,
    workspace: Workspace,
    user: User,
    role: WorkspaceRole,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = make_membership(
        workspace,
        user,
        role,
    )


async def test_member_can_create_draft_decision(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    grant_role(workspace_repository, workspace, user, WorkspaceRole.MEMBER)
    decision_repository.create.side_effect = lambda decision: decision

    decision = await service.create(
        user,
        workspace.id,
        DecisionCreateRequest(
            title="Choose the API framework",
            category="technology",
        ),
    )

    assert decision.status is DecisionStatus.DRAFT
    assert decision.created_by_id == user.id
    decision_repository.create.assert_awaited_once_with(decision)


async def test_viewer_cannot_create_decision(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    grant_role(workspace_repository, workspace, user, WorkspaceRole.VIEWER)

    with pytest.raises(DecisionAccessDeniedError):
        await service.create(
            user,
            workspace.id,
            DecisionCreateRequest(title="Choose the API framework"),
        )

    decision_repository.create.assert_not_awaited()


async def test_non_member_cannot_discover_workspace_decisions(
    service: DecisionService,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = None

    with pytest.raises(WorkspaceNotFoundError):
        await service.list_decisions(
            user,
            workspace.id,
            status=None,
            category=None,
            limit=50,
            offset=0,
        )


async def test_list_passes_filters_and_pagination(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    grant_role(workspace_repository, workspace, user, WorkspaceRole.VIEWER)
    decision_repository.list_for_workspace.return_value = []

    result = await service.list_decisions(
        user,
        workspace.id,
        status=DecisionStatus.ACTIVE,
        category=DecisionCategory.ARCHITECTURE,
        limit=20,
        offset=40,
    )

    assert result == []
    decision_repository.list_for_workspace.assert_awaited_once_with(
        workspace.id,
        status=DecisionStatus.ACTIVE,
        category=DecisionCategory.ARCHITECTURE,
        limit=20,
        offset=40,
    )


async def test_closed_decision_cannot_be_edited(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user, DecisionStatus.CLOSED)
    grant_role(workspace_repository, workspace, user, WorkspaceRole.MEMBER)
    decision_repository.get_for_workspace.return_value = decision

    with pytest.raises(DecisionImmutableError):
        await service.update(
            user,
            workspace.id,
            decision.id,
            DecisionUpdateRequest(title="Updated decision title"),
        )

    decision_repository.update.assert_not_awaited()


async def test_active_decision_can_be_closed(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user, DecisionStatus.ACTIVE)
    grant_role(workspace_repository, workspace, user, WorkspaceRole.MEMBER)
    decision_repository.get_for_workspace.return_value = decision
    decision_repository.transition.side_effect = lambda item, **values: item

    await service.transition(
        user,
        workspace.id,
        decision.id,
        DecisionTransitionRequest(status="closed"),
    )

    transition_values = decision_repository.transition.await_args.kwargs
    assert transition_values["status"] is DecisionStatus.CLOSED
    assert isinstance(transition_values["closed_at"], datetime)
    assert transition_values["closed_at"].tzinfo is UTC
    assert transition_values["archived_at"] is None


async def test_draft_cannot_skip_directly_to_closed(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    decision = make_decision(workspace, user)
    grant_role(workspace_repository, workspace, user, WorkspaceRole.MEMBER)
    decision_repository.get_for_workspace.return_value = decision

    with pytest.raises(DecisionInvalidTransitionError):
        await service.transition(
            user,
            workspace.id,
            decision.id,
            DecisionTransitionRequest(status="closed"),
        )

    decision_repository.transition.assert_not_awaited()


async def test_member_cannot_delete_decision(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    grant_role(workspace_repository, workspace, user, WorkspaceRole.MEMBER)

    with pytest.raises(DecisionAccessDeniedError):
        await service.delete(user, workspace.id, uuid4())

    decision_repository.delete.assert_not_awaited()


async def test_admin_can_delete_only_draft_decision(
    service: DecisionService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace()
    active_decision = make_decision(workspace, user, DecisionStatus.ACTIVE)
    grant_role(workspace_repository, workspace, user, WorkspaceRole.ADMIN)
    decision_repository.get_for_workspace.return_value = active_decision

    with pytest.raises(DecisionImmutableError):
        await service.delete(user, workspace.id, active_decision.id)

    decision_repository.delete.assert_not_awaited()
