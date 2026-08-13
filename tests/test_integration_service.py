from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.exceptions import IntegrationAccessDeniedError
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.integrations.providers.base import IntegrationProviderClient, ProviderInstallation
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationProvider,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.integration import IntegrationRepository
from app.repositories.integration_oauth import IntegrationOAuthStateRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.integration import IntegrationService


def make_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )


def make_service() -> tuple[
    IntegrationService,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    Mock,
    Mock,
]:
    integrations = AsyncMock(spec=IntegrationRepository)
    workspaces = AsyncMock(spec=WorkspaceRepository)
    oauth_states = AsyncMock(spec=IntegrationOAuthStateRepository)
    registry = Mock(spec=IntegrationProviderRegistry)
    provider = Mock(spec=IntegrationProviderClient)
    provider.provider = IntegrationProvider.SLACK
    provider.available = True
    provider.name = "Slack"
    provider.description = "Slack notifications"
    provider.capabilities = ("outbound_notifications", "channel_selection")
    provider.build_authorization_url.return_value = "https://slack.com/oauth/v2/authorize"
    provider.exchange_code = AsyncMock()
    provider.verify_connection = AsyncMock()
    provider.list_destinations = AsyncMock()
    provider.send_test_message = AsyncMock()
    provider.revoke = AsyncMock()
    registry.get.return_value = provider
    registry.list.return_value = [provider]
    settings = Settings(
        _env_file=None,
        frontend_url="https://forkroom.vercel.app",
        integration_token_encryption_key=Fernet.generate_key().decode("ascii"),
        slack_client_id="client-id",
        slack_client_secret="client-secret",
        slack_redirect_uri="https://api.example.com/api/v1/integrations/slack/callback",
    )
    service = IntegrationService(
        integrations,
        workspaces,
        oauth_states,
        registry,
        settings,
    )
    return service, integrations, workspaces, oauth_states, registry, provider


def grant_role(
    workspaces: AsyncMock,
    user: User,
    role: WorkspaceRole,
) -> Workspace:
    workspace = Workspace(id=uuid4(), name="ForkRoom", owner_id=uuid4())
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    return workspace


async def test_viewer_cannot_start_integration_oauth() -> None:
    service, _, workspaces, oauth_states, _, _ = make_service()
    user = make_user()
    workspace = grant_role(workspaces, user, WorkspaceRole.VIEWER)

    with pytest.raises(IntegrationAccessDeniedError):
        await service.authorize(user, workspace.id, IntegrationProvider.SLACK, None)

    oauth_states.issue.assert_not_awaited()


async def test_owner_can_start_oauth_with_server_stored_state() -> None:
    service, _, workspaces, oauth_states, _, provider = make_service()
    user = make_user()
    workspace = grant_role(workspaces, user, WorkspaceRole.OWNER)
    oauth_states.issue.return_value = "random-state"

    authorization_url, expires_at = await service.authorize(
        user,
        workspace.id,
        IntegrationProvider.SLACK,
        None,
    )

    assert authorization_url == "https://slack.com/oauth/v2/authorize"
    assert expires_at > datetime.now(UTC)
    stored_state = oauth_states.issue.await_args.args[0]
    assert stored_state.workspace_id == workspace.id
    assert stored_state.user_id == user.id
    assert stored_state.return_path == f"/w/{workspace.id}/integrations"
    assert len(stored_state.code_verifier) >= 43
    assert provider.build_authorization_url.call_args.kwargs["state"] == "random-state"


async def test_oauth_callback_encrypts_token_and_creates_subscriptions() -> None:
    service, integrations, workspaces, oauth_states, _, provider = make_service()
    user = make_user()
    workspace = grant_role(workspaces, user, WorkspaceRole.ADMIN)
    state_record = Mock()
    state_record.workspace_id = workspace.id
    state_record.user_id = user.id
    state_record.provider = IntegrationProvider.SLACK
    state_record.code_verifier = "pkce-verifier"
    state_record.return_path = f"/w/{workspace.id}/integrations"
    oauth_states.consume.return_value = state_record
    installation = ProviderInstallation(
        external_account_id="T123",
        external_account_name="ForkRoom Engineering",
        access_token="xoxb-secret",
        refresh_token=None,
        expires_at=None,
        scopes=["chat:write", "channels:read"],
        configuration={"bot_user_id": "B123"},
    )
    provider.exchange_code.return_value = installation
    connection = IntegrationConnection(
        id=uuid4(),
        workspace_id=workspace.id,
        provider=IntegrationProvider.SLACK,
        status=IntegrationConnectionStatus.ACTIVE,
        external_account_id="T123",
        external_account_name="ForkRoom Engineering",
        connected_by_id=user.id,
    )
    integrations.upsert_connection.return_value = connection

    redirect_url = await service.complete_authorization(
        IntegrationProvider.SLACK,
        state="random-state",
        code="temporary-code",
        provider_error=None,
    )

    assert redirect_url.endswith("?connected=slack")
    provider.verify_connection.assert_awaited_once_with("xoxb-secret")
    kwargs = integrations.upsert_connection.await_args.kwargs
    assert kwargs["access_token_encrypted"] != "xoxb-secret"
    assert "xoxb-secret" not in kwargs["access_token_encrypted"]
    integrations.ensure_subscriptions.assert_awaited_once_with(
        connection.id,
        service.supported_events,
    )
