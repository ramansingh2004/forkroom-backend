from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceMemberAlreadyExistsError,
    WorkspaceNotFoundError,
    WorkspaceOwnerImmutableError,
)
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_service
from app.main import app
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.workspace import WorkspaceMemberRecord
from app.services.workspace import WorkspaceService


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="not-returned",
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture
def workspace_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=WorkspaceService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_workspace_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_workspace_service, None)


async def test_create_workspace(
    client: AsyncClient,
    current_user: User,
    workspace_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    now = datetime(2026, 7, 28, tzinfo=UTC)
    workspace_service.create.return_value = Workspace(
        id=workspace_id,
        name="Backend Guild",
        description="Architecture decisions",
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )

    response = await client.post(
        "/api/v1/workspaces",
        json={
            "name": "  Backend   Guild  ",
            "description": "  Architecture   decisions  ",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(workspace_id),
        "name": "Backend Guild",
        "description": "Architecture decisions",
        "owner_id": str(current_user.id),
        "created_at": "2026-07-28T00:00:00Z",
        "updated_at": "2026-07-28T00:00:00Z",
    }
    payload = workspace_service.create.await_args.args[1]
    assert payload.name == "Backend Guild"


async def test_get_workspace_hides_inaccessible_workspace(
    client: AsyncClient,
    workspace_service: AsyncMock,
) -> None:
    workspace_service.get.side_effect = WorkspaceNotFoundError

    response = await client.get(f"/api/v1/workspaces/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


async def test_update_workspace_maps_permission_error(
    client: AsyncClient,
    workspace_service: AsyncMock,
) -> None:
    workspace_service.update.side_effect = WorkspaceAccessDeniedError

    response = await client.patch(
        f"/api/v1/workspaces/{uuid4()}",
        json={"name": "New name"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to perform this workspace action"
    }


async def test_add_workspace_member(
    client: AsyncClient,
    workspace_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    user = User(
        id=uuid4(),
        email="member@example.com",
        password_hash="not-returned",
        display_name="Workspace Member",
        avatar_url=None,
    )
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=user.id,
        role=WorkspaceRole.MEMBER,
        joined_at=datetime(2026, 7, 28, tzinfo=UTC),
    )
    workspace_service.add_member.return_value = WorkspaceMemberRecord(
        membership=membership,
        user=user,
    )

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={
            "email": "MEMBER@example.com",
            "role": "member",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "user_id": str(user.id),
        "email": "member@example.com",
        "display_name": "Workspace Member",
        "avatar_url": None,
        "role": "member",
        "joined_at": "2026-07-28T00:00:00Z",
    }


async def test_add_duplicate_workspace_member_returns_conflict(
    client: AsyncClient,
    workspace_service: AsyncMock,
) -> None:
    workspace_service.add_member.side_effect = WorkspaceMemberAlreadyExistsError

    response = await client.post(
        f"/api/v1/workspaces/{uuid4()}/members",
        json={
            "email": "member@example.com",
            "role": "viewer",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User is already a workspace member"}


async def test_owner_cannot_be_removed(
    client: AsyncClient,
    workspace_service: AsyncMock,
) -> None:
    workspace_service.remove_member.side_effect = WorkspaceOwnerImmutableError

    response = await client.delete(f"/api/v1/workspaces/{uuid4()}/members/{uuid4()}")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The workspace owner cannot be removed or assigned another role"
    }
