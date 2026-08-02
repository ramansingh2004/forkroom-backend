from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import DecisionNotFoundError, WorkspaceNotFoundError
from app.core.security import create_meeting_token, create_turn_credentials
from app.models.user import User
from app.models.workspace import WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.meeting import IceServer, MeetingPermission, MeetingTokenResponse


class MeetingService:
    def __init__(
        self,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def issue_token(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> MeetingTokenResponse:
        workspace = await self._workspaces.get_by_id(workspace_id)
        membership = await self._workspaces.get_membership(workspace_id, current_user.id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError

        can_facilitate = membership.role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
        if can_facilitate:
            permission = MeetingPermission.FACILITATE
        elif membership.role is WorkspaceRole.VIEWER:
            permission = MeetingPermission.OBSERVE
        else:
            permission = MeetingPermission.PARTICIPATE

        signed = create_meeting_token(
            user_id=current_user.id,
            workspace_id=workspace_id,
            decision_id=decision_id,
            display_name=current_user.display_name or current_user.email,
            role=membership.role.value,
            can_facilitate=can_facilitate,
        )
        settings = get_settings()
        turn_username, turn_credential, _ = create_turn_credentials(current_user.id)
        stun_urls = [url for url in settings.turn_urls if url.startswith("stun:")]
        relay_urls = [url for url in settings.turn_urls if url.startswith("turn:")]
        ice_servers = [IceServer(urls=stun_urls)] if stun_urls else []
        if relay_urls:
            ice_servers.append(
                IceServer(
                    urls=relay_urls,
                    username=turn_username,
                    credential=turn_credential,
                )
            )
        return MeetingTokenResponse(
            token=signed.token,
            expires_in=signed.expires_in,
            expires_at=signed.expires_at,
            websocket_url=f"{settings.meeting_websocket_url}/{workspace_id}/{decision_id}",
            permission=permission,
            max_participants=settings.meeting_max_participants,
            ice_servers=ice_servers,
        )
