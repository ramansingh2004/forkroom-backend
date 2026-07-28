from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    ObjectionAccessDeniedError,
    ObjectionInvalidTransitionError,
)
from app.dependencies.auth import get_current_user
from app.dependencies.objection import get_objection_service
from app.main import app
from app.models.objection import (
    Objection,
    ObjectionSeverity,
    ObjectionStatus,
    ObjectionStatusEvent,
)
from app.models.user import User
from app.services.objection import ObjectionService


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
def objection_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=ObjectionService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_objection_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_objection_service, None)


def objection_path(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
) -> str:
    return (
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}"
        f"/proposals/{proposal_id}/objections"
    )


def make_objection(user: User, proposal_id: UUID) -> Objection:
    now = datetime(2026, 7, 29, tzinfo=UTC)
    return Objection(
        id=uuid4(),
        proposal_id=proposal_id,
        created_by_id=user.id,
        severity=ObjectionSeverity.BLOCKING,
        status=ObjectionStatus.OPEN,
        title="Migration safety is unclear",
        description="The proposal does not explain rollback behavior.",
        resolution_note=None,
        resolved_by_id=None,
        resolved_at=None,
        created_at=now,
        updated_at=now,
    )


async def test_create_structured_objection(
    client: AsyncClient,
    current_user: User,
    objection_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal_id = uuid4()
    objection = make_objection(current_user, proposal_id)
    objection_service.create.return_value = objection

    response = await client.post(
        objection_path(workspace_id, decision_id, proposal_id),
        json={
            "severity": "blocking",
            "title": "  Migration   safety is unclear ",
            "description": " The proposal does not explain rollback behavior. ",
        },
    )

    assert response.status_code == 201
    assert response.json()["severity"] == "blocking"
    assert response.json()["status"] == "open"
    payload = objection_service.create.await_args.args[4]
    assert payload.title == "Migration safety is unclear"


async def test_list_objections_forwards_filters(
    client: AsyncClient,
    objection_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal_id = uuid4()
    objection_service.list_objections.return_value = []

    response = await client.get(
        objection_path(workspace_id, decision_id, proposal_id),
        params={"severity": "major", "status": "open"},
    )

    assert response.status_code == 200
    assert response.json() == []
    assert objection_service.list_objections.await_args.kwargs == {
        "severity": ObjectionSeverity.MAJOR,
        "status": ObjectionStatus.OPEN,
    }


async def test_transition_objection(
    client: AsyncClient,
    current_user: User,
    objection_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal_id = uuid4()
    objection = make_objection(current_user, proposal_id)
    objection.status = ObjectionStatus.RESOLVED
    objection.resolution_note = "Rollback steps were added."
    objection.resolved_by_id = current_user.id
    objection.resolved_at = datetime(2026, 7, 29, tzinfo=UTC)
    objection_service.transition.return_value = objection

    response = await client.post(
        (f"{objection_path(workspace_id, decision_id, proposal_id)}/{objection.id}/transitions"),
        json={
            "status": "resolved",
            "note": "Rollback steps were added.",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["resolution_note"] == "Rollback steps were added."


async def test_objection_permission_error_returns_forbidden(
    client: AsyncClient,
    objection_service: AsyncMock,
) -> None:
    objection_service.create.side_effect = ObjectionAccessDeniedError

    response = await client.post(
        objection_path(uuid4(), uuid4(), uuid4()),
        json={
            "severity": "major",
            "title": "Insufficient evidence",
            "description": "The benchmark does not cover expected production load.",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to perform this objection action"
    }


async def test_invalid_transition_returns_conflict(
    client: AsyncClient,
    objection_service: AsyncMock,
) -> None:
    objection_service.transition.side_effect = ObjectionInvalidTransitionError

    response = await client.post(
        f"{objection_path(uuid4(), uuid4(), uuid4())}/{uuid4()}/transitions",
        json={
            "status": "open",
            "note": "Keep the existing concern open.",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "The requested objection status transition is invalid"}


async def test_list_objection_resolution_history(
    client: AsyncClient,
    current_user: User,
    objection_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal_id = uuid4()
    objection_id = uuid4()
    now = datetime(2026, 7, 29, tzinfo=UTC)
    event = ObjectionStatusEvent(
        id=uuid4(),
        objection_id=objection_id,
        actor_id=current_user.id,
        from_status=ObjectionStatus.OPEN,
        to_status=ObjectionStatus.RESOLVED,
        note="Rollback steps were added.",
        created_at=now,
    )
    objection_service.list_history.return_value = [event]

    response = await client.get(
        f"{objection_path(workspace_id, decision_id, proposal_id)}/{objection_id}/history"
    )

    assert response.status_code == 200
    assert response.json()[0]["from_status"] == "open"
    assert response.json()[0]["to_status"] == "resolved"
