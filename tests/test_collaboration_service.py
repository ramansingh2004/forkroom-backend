from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import WorkspaceNotFoundError
from app.models.collaboration import CollaborationDocument
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.collaboration import CollaborationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.collaboration import CollaborationPermission
from app.services.collaboration import CollaborationService


def make_service() -> tuple[CollaborationService, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    documents = AsyncMock(spec=CollaborationRepository)
    proposals = AsyncMock(spec=ProposalRepository)
    decisions = AsyncMock(spec=DecisionRepository)
    workspaces = AsyncMock(spec=WorkspaceRepository)
    return (
        CollaborationService(documents, proposals, decisions, workspaces),
        documents,
        proposals,
        decisions,
        workspaces,
    )


def grant_context(
    documents: AsyncMock,
    proposals: AsyncMock,
    decisions: AsyncMock,
    workspaces: AsyncMock,
    *,
    role: WorkspaceRole,
    proposal_status: ProposalStatus,
) -> tuple[User, Workspace, Decision, Proposal, CollaborationDocument]:
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
        title="Choose the API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.ACTIVE,
    )
    proposal = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        title="Use FastAPI",
        status=proposal_status,
    )
    document = CollaborationDocument(
        id=uuid4(),
        workspace_id=workspace.id,
        decision_id=decision.id,
        proposal_id=proposal.id,
        document_name=f"proposal:{proposal.id}",
        state_version=0,
    )
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    decisions.get_for_workspace.return_value = decision
    proposals.get_for_decision.return_value = proposal
    documents.get_or_create.return_value = document
    return user, workspace, decision, proposal, document


async def test_member_receives_short_lived_write_token_for_draft() -> None:
    service, documents, proposals, decisions, workspaces = make_service()
    user, workspace, decision, proposal, document = grant_context(
        documents,
        proposals,
        decisions,
        workspaces,
        role=WorkspaceRole.MEMBER,
        proposal_status=ProposalStatus.DRAFT,
    )

    response = await service.issue_token(user, workspace.id, decision.id, proposal.id)

    assert response.permission is CollaborationPermission.WRITE
    assert response.document_name == document.document_name
    assert response.expires_in == 300
    claims = jwt.decode(
        response.token,
        get_settings().jwt_collaboration_secret,
        algorithms=["HS256"],
        audience="forkroom-collaboration",
        issuer="forkroom-api",
    )
    assert claims["document_name"] == document.document_name
    assert claims["permission"] == "write"
    assert claims["sub"] == str(user.id)


async def test_viewer_receives_read_only_token() -> None:
    service, documents, proposals, decisions, workspaces = make_service()
    user, workspace, decision, proposal, _ = grant_context(
        documents,
        proposals,
        decisions,
        workspaces,
        role=WorkspaceRole.VIEWER,
        proposal_status=ProposalStatus.DRAFT,
    )
    response = await service.issue_token(user, workspace.id, decision.id, proposal.id)
    assert response.permission is CollaborationPermission.READ


async def test_submitted_proposal_is_read_only() -> None:
    service, documents, proposals, decisions, workspaces = make_service()
    user, workspace, decision, proposal, _ = grant_context(
        documents,
        proposals,
        decisions,
        workspaces,
        role=WorkspaceRole.ADMIN,
        proposal_status=ProposalStatus.SUBMITTED,
    )
    response = await service.issue_token(user, workspace.id, decision.id, proposal.id)
    assert response.permission is CollaborationPermission.READ


async def test_non_member_cannot_discover_workspace() -> None:
    service, _, _, _, workspaces = make_service()
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
        await service.issue_token(user, uuid4(), uuid4(), uuid4())
