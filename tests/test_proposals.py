from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import CriterionConflictError, ProposalImmutableError
from app.dependencies.auth import get_current_user
from app.dependencies.proposal import get_proposal_service
from app.main import app
from app.models.proposal import DecisionCriterion, Proposal, ProposalStatus
from app.models.user import User
from app.services.proposal import ProposalService


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
def proposal_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=ProposalService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_proposal_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_proposal_service, None)


def make_proposal(user: User, decision_id: object) -> Proposal:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    return Proposal(
        id=uuid4(),
        decision_id=decision_id,
        created_by_id=user.id,
        title="Use FastAPI",
        summary="Strong async API support.",
        content="Detailed proposal content.",
        status=ProposalStatus.DRAFT,
        submitted_at=None,
        withdrawn_at=None,
        created_at=now,
        updated_at=now,
    )


async def test_create_proposal_branch(
    client: AsyncClient,
    current_user: User,
    proposal_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal = make_proposal(current_user, decision_id)
    proposal_service.create.return_value = proposal

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/proposals",
        json={
            "title": "  Use   FastAPI  ",
            "summary": "  Strong async API support.  ",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    payload = proposal_service.create.await_args.args[3]
    assert payload.title == "Use FastAPI"


async def test_list_proposals_forwards_status_filter(
    client: AsyncClient,
    proposal_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    proposal_service.list_proposals.return_value = []

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/proposals",
        params={"status": "submitted"},
    )

    assert response.status_code == 200
    assert response.json() == []
    assert proposal_service.list_proposals.await_args.kwargs == {"status": ProposalStatus.SUBMITTED}


async def test_immutable_proposal_returns_conflict(
    client: AsyncClient,
    proposal_service: AsyncMock,
) -> None:
    proposal_service.update.side_effect = ProposalImmutableError

    response = await client.patch(
        (f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}/proposals/{uuid4()}"),
        json={"title": "Updated proposal"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "The proposal or its parent decision cannot be changed"}


async def test_create_weighted_criterion(
    client: AsyncClient,
    current_user: User,
    proposal_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    now = datetime(2026, 7, 28, tzinfo=UTC)
    criterion = DecisionCriterion(
        id=uuid4(),
        decision_id=decision_id,
        created_by_id=current_user.id,
        name="Operational complexity",
        description=None,
        weight=3,
        position=0,
        created_at=now,
        updated_at=now,
    )
    proposal_service.create_criterion.return_value = criterion

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/criteria",
        json={"name": "Operational complexity", "weight": 3},
    )

    assert response.status_code == 201
    assert response.json()["weight"] == 3
    assert response.json()["position"] == 0


async def test_invalid_criterion_order_returns_conflict(
    client: AsyncClient,
    proposal_service: AsyncMock,
) -> None:
    proposal_service.reorder_criteria.side_effect = CriterionConflictError

    response = await client.put(
        f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}/criteria/order",
        json={"criterion_ids": [str(uuid4())]},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The requested proposal state or criterion order is invalid"
    }


async def test_delete_draft_proposal(
    client: AsyncClient,
    proposal_service: AsyncMock,
) -> None:
    response = await client.delete(
        f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}/proposals/{uuid4()}"
    )

    assert response.status_code == 204
    assert response.content == b""
    proposal_service.delete.assert_awaited_once()
