from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.auth import get_current_user
from app.dependencies.meeting import get_meeting_service
from app.main import app
from app.models.user import User
from app.schemas.meeting import IceServer, MeetingPermission, MeetingTokenResponse
from app.services.meeting import MeetingService


@pytest.fixture
def meeting_service() -> Iterator[AsyncMock]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )
    service = AsyncMock(spec=MeetingService)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_meeting_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_meeting_service, None)


async def test_issue_meeting_token_endpoint(
    client: AsyncClient,
    meeting_service: AsyncMock,
) -> None:
    workspace_id, decision_id = uuid4(), uuid4()
    meeting_service.issue_token.return_value = MeetingTokenResponse(
        token="signed-meeting-token",
        expires_in=300,
        expires_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        websocket_url=f"ws://localhost:8000/api/v1/ws/meetings/{workspace_id}/{decision_id}",
        permission=MeetingPermission.PARTICIPATE,
        max_participants=4,
        ice_servers=[IceServer(urls=["stun:localhost:3478"])],
    )
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/meeting-token"
    )
    assert response.status_code == 200
    assert response.json()["permission"] == "participate"
    assert response.json()["max_participants"] == 4
