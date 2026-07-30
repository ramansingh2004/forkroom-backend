from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.auth import get_current_user
from app.dependencies.collaboration import get_collaboration_service
from app.main import app
from app.models.user import User
from app.schemas.collaboration import (
    CollaborationPermission,
    CollaborationTokenResponse,
)
from app.services.collaboration import CollaborationService


@pytest.fixture
def collaboration_service() -> Iterator[AsyncMock]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )
    service = AsyncMock(spec=CollaborationService)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_collaboration_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_collaboration_service, None)


async def test_issue_collaboration_token_endpoint(
    client: AsyncClient,
    collaboration_service: AsyncMock,
) -> None:
    workspace_id, decision_id, proposal_id, document_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    collaboration_service.issue_token.return_value = CollaborationTokenResponse(
        token="signed-token",
        expires_in=300,
        expires_at=datetime(2026, 7, 30, 3, 5, tzinfo=UTC),
        collaboration_url="ws://localhost:1234",
        document_id=document_id,
        document_name=f"proposal:{proposal_id}",
        permission=CollaborationPermission.WRITE,
    )
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/"
        f"proposals/{proposal_id}/collaboration-token"
    )
    assert response.status_code == 200
    assert response.json()["permission"] == "write"
    assert response.json()["expires_in"] == 300
