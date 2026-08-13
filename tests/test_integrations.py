from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.auth import get_current_user
from app.dependencies.integration import get_integration_service
from app.main import app
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationProvider,
)
from app.models.user import User
from app.services.integration import IntegrationService


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
def integration_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=IntegrationService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_integration_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_integration_service, None)


async def test_provider_catalog_never_returns_credentials(
    client: AsyncClient,
    integration_service: AsyncMock,
) -> None:
    provider = Mock()
    provider.provider = IntegrationProvider.SLACK
    provider.name = "Slack"
    provider.description = "Send decision updates to Slack channels."
    provider.capabilities = ("outbound_notifications", "channel_selection")
    integration_service.provider_catalog.return_value = [(provider, True)]

    response = await client.get("/api/v1/integrations/providers")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "provider": "slack",
                "name": "Slack",
                "description": "Send decision updates to Slack channels.",
                "available": True,
                "capabilities": ["outbound_notifications", "channel_selection"],
            }
        ]
    }
    assert "token" not in response.text.lower()
    assert "secret" not in response.text.lower()


async def test_list_workspace_connections_omits_encrypted_tokens(
    client: AsyncClient,
    current_user: User,
    integration_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    connection_id = uuid4()
    now = datetime(2026, 8, 13, tzinfo=UTC)
    integration_service.list_connections.return_value = [
        IntegrationConnection(
            id=connection_id,
            workspace_id=workspace_id,
            provider=IntegrationProvider.SLACK,
            status=IntegrationConnectionStatus.ACTIVE,
            external_account_id="T123",
            external_account_name="ForkRoom Engineering",
            access_token_encrypted="encrypted-secret",
            scopes=["chat:write"],
            configuration={"bot_user_id": "B123"},
            connected_by_id=current_user.id,
            created_at=now,
            updated_at=now,
        )
    ]

    response = await client.get(f"/api/v1/workspaces/{workspace_id}/integrations")

    assert response.status_code == 200
    payload = response.json()["items"][0]
    assert payload["id"] == str(connection_id)
    assert payload["external_account_name"] == "ForkRoom Engineering"
    assert "access_token_encrypted" not in payload
    assert "refresh_token_encrypted" not in payload


async def test_slack_callback_redirects_to_frontend(
    client: AsyncClient,
    integration_service: AsyncMock,
) -> None:
    integration_service.complete_authorization.return_value = (
        "https://forkroom.vercel.app/w/workspace/integrations?connected=slack"
    )

    response = await client.get(
        "/api/v1/integrations/slack/callback",
        params={"state": "state", "code": "code"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://forkroom.vercel.app/w/workspace/integrations?connected=slack"
    )
