from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
    WorkspaceOwnerImmutableError,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceUpdateRequest,
)
from app.services.workspace import WorkspaceService


@pytest.fixture
def workspace_repository() -> AsyncMock:
    return AsyncMock(spec=WorkspaceRepository)


@pytest.fixture
def user_repository() -> AsyncMock:
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def service(
    workspace_repository: AsyncMock,
    user_repository: AsyncMock,
) -> WorkspaceService:
    return WorkspaceService(
        workspace_repository,
        user_repository,
    )


def make_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="password-hash",
        display_name="Raman Singh",
        is_active=True,
    )


def make_workspace(owner_id: object) -> Workspace:
    return Workspace(
        id=uuid4(),
        name="Backend Guild",
        owner_id=owner_id,
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


async def test_create_workspace_also_assigns_owner(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace_repository.create.side_effect = lambda workspace: workspace

    workspace = await service.create(
        user,
        WorkspaceCreateRequest(
            name="Backend Guild",
            description="Architecture decisions",
        ),
    )

    assert workspace.owner_id == user.id
    assert workspace.name == "Backend Guild"
    workspace_repository.create.assert_awaited_once_with(workspace)


async def test_non_member_cannot_discover_workspace(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace(user.id)
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = None

    with pytest.raises(WorkspaceNotFoundError):
        await service.get(user, workspace.id)


async def test_viewer_cannot_update_workspace(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
) -> None:
    user = make_user()
    workspace = make_workspace(uuid4())
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = make_membership(
        workspace,
        user,
        WorkspaceRole.VIEWER,
    )

    with pytest.raises(WorkspaceAccessDeniedError):
        await service.update(
            user,
            workspace.id,
            WorkspaceUpdateRequest(name="Updated name"),
        )

    workspace_repository.update.assert_not_awaited()


async def test_admin_can_add_member(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
    user_repository: AsyncMock,
) -> None:
    actor = make_user()
    target = User(
        id=uuid4(),
        email="member@example.com",
        password_hash="password-hash",
        display_name="Workspace Member",
        is_active=True,
    )
    workspace = make_workspace(uuid4())
    actor_membership = make_membership(
        workspace,
        actor,
        WorkspaceRole.ADMIN,
    )
    target_membership = make_membership(
        workspace,
        target,
        WorkspaceRole.MEMBER,
    )
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = actor_membership
    workspace_repository.add_member.return_value = target_membership
    user_repository.get_by_email.return_value = target

    result = await service.add_member(
        actor,
        workspace.id,
        WorkspaceMemberCreateRequest(
            email="member@example.com",
            role="member",
        ),
    )

    assert result.user is target
    workspace_repository.add_member.assert_awaited_once_with(
        workspace.id,
        target.id,
        WorkspaceRole.MEMBER,
    )


async def test_admin_cannot_change_member_roles(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
) -> None:
    actor = make_user()
    target = make_user()
    workspace = make_workspace(uuid4())
    actor_membership = make_membership(
        workspace,
        actor,
        WorkspaceRole.ADMIN,
    )
    target_membership = make_membership(
        workspace,
        target,
        WorkspaceRole.MEMBER,
    )
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.side_effect = [
        actor_membership,
        target_membership,
    ]

    with pytest.raises(WorkspaceAccessDeniedError):
        await service.update_member_role(
            actor,
            workspace.id,
            target.id,
            WorkspaceMemberUpdateRequest(role="viewer"),
        )


async def test_owner_membership_cannot_be_changed(
    service: WorkspaceService,
    workspace_repository: AsyncMock,
) -> None:
    owner = make_user()
    workspace = make_workspace(owner.id)
    owner_membership = make_membership(
        workspace,
        owner,
        WorkspaceRole.OWNER,
    )
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.side_effect = [
        owner_membership,
        owner_membership,
    ]

    with pytest.raises(WorkspaceOwnerImmutableError):
        await service.update_member_role(
            owner,
            workspace.id,
            owner.id,
            WorkspaceMemberUpdateRequest(role="admin"),
        )
