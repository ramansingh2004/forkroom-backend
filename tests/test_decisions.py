from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionInvalidTransitionError,
    WorkspaceNotFoundError,
)
from app.dependencies.auth import get_current_user
from app.dependencies.decision import get_decision_service
from app.main import app
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.user import User
from app.services.decision import DecisionService


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
def decision_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=DecisionService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_decision_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_decision_service, None)


def make_decision(user: User, workspace_id: object) -> Decision:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    return Decision(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by_id=user.id,
        title="Choose the API framework",
        summary="Compare FastAPI and Django for ForkRoom.",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.DRAFT,
        due_at=None,
        review_at=None,
        closed_at=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )


async def test_create_decision(
    client: AsyncClient,
    current_user: User,
    decision_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision = make_decision(current_user, workspace_id)
    decision_service.create.return_value = decision

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions",
        json={
            "title": "  Choose   the API framework  ",
            "summary": "  Compare FastAPI and Django for ForkRoom.  ",
            "category": "technology",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(decision.id)
    assert response.json()["status"] == "draft"
    payload = decision_service.create.await_args.args[2]
    assert payload.title == "Choose the API framework"


async def test_list_decisions_forwards_filters(
    client: AsyncClient,
    decision_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_service.list_decisions.return_value = []

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/decisions",
        params={
            "status": "active",
            "category": "architecture",
            "limit": 20,
            "offset": 40,
        },
    )

    assert response.status_code == 200
    assert response.json() == []
    decision_service.list_decisions.assert_awaited_once()
    arguments = decision_service.list_decisions.await_args
    assert arguments.kwargs == {
        "status": DecisionStatus.ACTIVE,
        "category": DecisionCategory.ARCHITECTURE,
        "limit": 20,
        "offset": 40,
    }


async def test_inaccessible_workspace_is_hidden(
    client: AsyncClient,
    decision_service: AsyncMock,
) -> None:
    decision_service.list_decisions.side_effect = WorkspaceNotFoundError

    response = await client.get(f"/api/v1/workspaces/{uuid4()}/decisions")

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


async def test_invalid_transition_returns_conflict(
    client: AsyncClient,
    decision_service: AsyncMock,
) -> None:
    decision_service.transition.side_effect = DecisionInvalidTransitionError

    response = await client.post(
        f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}/transitions",
        json={"status": "closed"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "The requested decision state or schedule is invalid"}


async def test_closed_decision_update_returns_conflict(
    client: AsyncClient,
    decision_service: AsyncMock,
) -> None:
    decision_service.update.side_effect = DecisionImmutableError

    response = await client.patch(
        f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}",
        json={"title": "Updated decision"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Closed or archived decisions cannot be changed"}


async def test_delete_draft_decision(
    client: AsyncClient,
    decision_service: AsyncMock,
) -> None:
    response = await client.delete(f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}")

    assert response.status_code == 204
    assert response.content == b""
    decision_service.delete.assert_awaited_once()
