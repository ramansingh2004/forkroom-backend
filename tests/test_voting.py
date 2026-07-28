from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    VoteAlreadyCastError,
    VotingBlockedByObjectionsError,
    VotingResultUnavailableError,
)
from app.dependencies.auth import get_current_user
from app.dependencies.voting import get_voting_service
from app.main import app
from app.models.user import User
from app.models.voting import Vote, VotingSession, VotingSessionStatus
from app.schemas.voting import (
    ProposalVoteTallyResponse,
    VotingResultResponse,
)
from app.services.voting import VotingService


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
def voting_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=VotingService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_voting_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_voting_service, None)


def voting_path(workspace_id: UUID, decision_id: UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/voting-sessions"


def make_voting_session(
    user: User,
    decision_id: UUID,
    *,
    status: VotingSessionStatus = VotingSessionStatus.DRAFT,
) -> VotingSession:
    now = datetime(2026, 7, 29, tzinfo=UTC)
    return VotingSession(
        id=uuid4(),
        decision_id=decision_id,
        created_by_id=user.id,
        status=status,
        quorum_percentage=60,
        eligible_voter_count=0,
        opened_at=now if status is not VotingSessionStatus.DRAFT else None,
        closes_at=None,
        closed_at=now if status is VotingSessionStatus.CLOSED else None,
        cancelled_at=now if status is VotingSessionStatus.CANCELLED else None,
        created_at=now,
        updated_at=now,
    )


async def test_create_voting_session(
    client: AsyncClient,
    current_user: User,
    voting_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    voting_session = make_voting_session(current_user, decision_id)
    voting_service.create_session.return_value = voting_session

    response = await client.post(
        voting_path(workspace_id, decision_id),
        json={"quorum_percentage": 70},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["quorum_percentage"] == 60
    payload = voting_service.create_session.await_args.args[3]
    assert payload.quorum_percentage == 70


async def test_open_voting_session(
    client: AsyncClient,
    current_user: User,
    voting_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    voting_session = make_voting_session(
        current_user,
        decision_id,
        status=VotingSessionStatus.OPEN,
    )
    voting_session.eligible_voter_count = 4
    voting_service.open_session.return_value = voting_session

    response = await client.post(
        f"{voting_path(workspace_id, decision_id)}/{voting_session.id}/open"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "open"
    assert response.json()["eligible_voter_count"] == 4


async def test_cast_vote(
    client: AsyncClient,
    current_user: User,
    voting_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    voting_session_id = uuid4()
    proposal_id = uuid4()
    now = datetime(2026, 7, 29, tzinfo=UTC)
    vote = Vote(
        id=uuid4(),
        voting_session_id=voting_session_id,
        voter_id=current_user.id,
        proposal_id=proposal_id,
        created_at=now,
    )
    voting_service.cast_vote.return_value = vote

    response = await client.post(
        f"{voting_path(workspace_id, decision_id)}/{voting_session_id}/votes",
        json={"proposal_id": str(proposal_id)},
    )

    assert response.status_code == 201
    assert response.json()["proposal_id"] == str(proposal_id)


async def test_blocking_objection_returns_conflict(
    client: AsyncClient,
    voting_service: AsyncMock,
) -> None:
    voting_service.open_session.side_effect = VotingBlockedByObjectionsError

    response = await client.post(f"{voting_path(uuid4(), uuid4())}/{uuid4()}/open")

    assert response.status_code == 409
    assert response.json() == {"detail": "Resolve every blocking objection before opening voting"}


async def test_duplicate_vote_returns_conflict(
    client: AsyncClient,
    voting_service: AsyncMock,
) -> None:
    voting_service.cast_vote.side_effect = VoteAlreadyCastError

    response = await client.post(
        f"{voting_path(uuid4(), uuid4())}/{uuid4()}/votes",
        json={"proposal_id": str(uuid4())},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "You have already voted in this session"}


async def test_get_closed_voting_result(
    client: AsyncClient,
    voting_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    voting_session_id = uuid4()
    winner_id = uuid4()
    voting_service.get_result.return_value = VotingResultResponse(
        voting_session_id=voting_session_id,
        eligible_voter_count=5,
        votes_cast=4,
        quorum_percentage=60,
        required_votes=3,
        quorum_met=True,
        result_valid=True,
        winner_proposal_id=winner_id,
        is_tie=False,
        tallies=[
            ProposalVoteTallyResponse(
                proposal_id=winner_id,
                votes=4,
                percentage=100.0,
            )
        ],
    )

    response = await client.get(
        f"{voting_path(workspace_id, decision_id)}/{voting_session_id}/result"
    )

    assert response.status_code == 200
    assert response.json()["quorum_met"] is True
    assert response.json()["winner_proposal_id"] == str(winner_id)


async def test_open_result_is_unavailable(
    client: AsyncClient,
    voting_service: AsyncMock,
) -> None:
    voting_service.get_result.side_effect = VotingResultUnavailableError

    response = await client.get(f"{voting_path(uuid4(), uuid4())}/{uuid4()}/result")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Voting results are available only after the session closes"
    }
