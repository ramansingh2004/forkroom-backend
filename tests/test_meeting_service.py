from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import WorkspaceNotFoundError
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.meeting import MeetingPermission
from app.services.meeting import MeetingService


def make_service() -> tuple[MeetingService, AsyncMock, AsyncMock]:
    decisions = AsyncMock(spec=DecisionRepository)
    workspaces = AsyncMock(spec=WorkspaceRepository)
    return MeetingService(decisions, workspaces), decisions, workspaces


def grant_context(
    decisions: AsyncMock,
    workspaces: AsyncMock,
    role: WorkspaceRole,
) -> tuple[User, Workspace, Decision]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=user.id)
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose meeting transport",
        category=DecisionCategory.ARCHITECTURE,
        status=DecisionStatus.ACTIVE,
    )
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = WorkspaceMember(
        id=uuid4(), workspace_id=workspace.id, user_id=user.id, role=role
    )
    decisions.get_for_workspace.return_value = decision
    return user, workspace, decision


async def test_admin_receives_facilitator_token_and_turn_credentials() -> None:
    service, decisions, workspaces = make_service()
    user, workspace, decision = grant_context(decisions, workspaces, WorkspaceRole.ADMIN)

    response = await service.issue_token(user, workspace.id, decision.id)

    assert response.permission is MeetingPermission.FACILITATE
    assert response.max_participants == 4
    assert len(response.ice_servers) == 2
    assert response.ice_servers[1].username is not None
    assert response.ice_servers[1].credential is not None
    claims = jwt.decode(
        response.token,
        get_settings().jwt_collaboration_secret,
        algorithms=["HS256"],
        audience="forkroom-meeting",
        issuer="forkroom-api",
    )
    assert claims["decision_id"] == str(decision.id)
    assert claims["can_facilitate"] is True


async def test_viewer_receives_observer_permission() -> None:
    service, decisions, workspaces = make_service()
    user, workspace, decision = grant_context(decisions, workspaces, WorkspaceRole.VIEWER)
    response = await service.issue_token(user, workspace.id, decision.id)
    assert response.permission is MeetingPermission.OBSERVE


async def test_non_member_cannot_obtain_meeting_token() -> None:
    service, _, workspaces = make_service()
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )
    workspaces.get_by_id.return_value = Workspace(id=uuid4(), name="Private", owner_id=uuid4())
    workspaces.get_membership.return_value = None
    with pytest.raises(WorkspaceNotFoundError):
        await service.issue_token(user, uuid4(), uuid4())
