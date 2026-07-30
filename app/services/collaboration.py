from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import (
    DecisionNotFoundError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)
from app.core.security import create_collaboration_token
from app.models.decision import DecisionStatus
from app.models.proposal import ProposalStatus
from app.models.user import User
from app.models.workspace import WorkspaceRole
from app.repositories.collaboration import CollaborationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.collaboration import CollaborationPermission, CollaborationTokenResponse


class CollaborationService:
    def __init__(
        self,
        collaboration_repository: CollaborationRepository,
        proposal_repository: ProposalRepository,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._documents = collaboration_repository
        self._proposals = proposal_repository
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def issue_token(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> CollaborationTokenResponse:
        workspace = await self._workspaces.get_by_id(workspace_id)
        membership = await self._workspaces.get_membership(workspace_id, current_user.id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        proposal = await self._proposals.get_for_decision(decision_id, proposal_id)
        if proposal is None:
            raise ProposalNotFoundError

        can_write = (
            decision.status in {DecisionStatus.DRAFT, DecisionStatus.ACTIVE}
            and proposal.status is ProposalStatus.DRAFT
            and membership.role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER}
        )
        permission = CollaborationPermission.WRITE if can_write else CollaborationPermission.READ
        document = await self._documents.get_or_create(
            workspace_id=workspace_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
        )
        signed = create_collaboration_token(
            user_id=current_user.id,
            workspace_id=workspace_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
            document_name=document.document_name,
            permission=permission.value,
            display_name=current_user.display_name or current_user.email,
        )
        return CollaborationTokenResponse(
            token=signed.token,
            expires_in=signed.expires_in,
            expires_at=signed.expires_at,
            collaboration_url=get_settings().collaboration_url,
            document_id=document.id,
            document_name=document.document_name,
            permission=permission,
        )
