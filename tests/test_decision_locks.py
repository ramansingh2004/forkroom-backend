from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    DecisionLockAccessDeniedError,
    DecisionLockInvalidResultError,
)
from app.dependencies.auth import get_current_user
from app.dependencies.decision_lock import get_decision_lock_service
from app.main import app
from app.models.decision import DecisionLock
from app.models.user import User
from app.schemas.decision_lock import DecisionLockVerificationResponse
from app.services.decision_lock import DecisionLockService


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
def lock_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=DecisionLockService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_decision_lock_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_decision_lock_service, None)


def lock_path(workspace_id: UUID, decision_id: UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/lock"


def make_lock(user: User, decision_id: UUID) -> DecisionLock:
    now = datetime(2026, 7, 29, tzinfo=UTC)
    snapshot: dict[str, object] = {
        "approved_proposal": {"title": "Use FastAPI"},
        "voting_result": {"quorum_met": True},
        "dissent": {"alternative_proposals": []},
    }
    return DecisionLock(
        id=uuid4(),
        decision_id=decision_id,
        voting_session_id=uuid4(),
        winning_proposal_id=uuid4(),
        locked_by_id=user.id,
        snapshot_version=1,
        snapshot=snapshot,
        document_hash=DecisionLockService.hash_snapshot(snapshot),
        locked_at=now,
    )


async def test_create_decision_lock(
    client: AsyncClient,
    current_user: User,
    lock_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    decision_lock = make_lock(current_user, decision_id)
    lock_service.create.return_value = decision_lock

    response = await client.post(
        lock_path(workspace_id, decision_id),
        json={"voting_session_id": str(decision_lock.voting_session_id)},
    )

    assert response.status_code == 201
    assert response.json()["winning_proposal_id"] == str(decision_lock.winning_proposal_id)
    assert len(response.json()["document_hash"]) == 64


async def test_get_decision_lock(
    client: AsyncClient,
    current_user: User,
    lock_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    lock_service.get.return_value = make_lock(current_user, decision_id)

    response = await client.get(lock_path(workspace_id, decision_id))

    assert response.status_code == 200
    assert response.json()["snapshot_version"] == 1


async def test_verify_decision_lock(
    client: AsyncClient,
    lock_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    document_hash = "a" * 64
    lock_service.verify.return_value = DecisionLockVerificationResponse(
        decision_id=decision_id,
        document_hash=document_hash,
        computed_hash=document_hash,
        valid=True,
    )

    response = await client.get(f"{lock_path(workspace_id, decision_id)}/verify")

    assert response.status_code == 200
    assert response.json()["valid"] is True


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            DecisionLockAccessDeniedError(),
            403,
            "Only workspace owners and admins can lock decisions",
        ),
        (
            DecisionLockInvalidResultError(),
            409,
            "The decision cannot be locked from this voting result",
        ),
    ],
)
async def test_lock_errors_are_mapped(
    error: Exception,
    status_code: int,
    detail: str,
    client: AsyncClient,
    lock_service: AsyncMock,
) -> None:
    lock_service.create.side_effect = error

    response = await client.post(
        lock_path(uuid4(), uuid4()),
        json={"voting_session_id": str(uuid4())},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
