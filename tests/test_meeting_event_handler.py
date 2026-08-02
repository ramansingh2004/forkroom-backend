from unittest.mock import AsyncMock
from uuid import uuid4

from app.core.security import MeetingTokenClaims
from app.repositories.meeting import MeetingRoomRepository
from app.routes.v1.meetings import _handle_client_event
from app.schemas.meeting import MeetingClientEvent


def claims(*, can_facilitate: bool, role: str = "member") -> MeetingTokenClaims:
    from datetime import UTC, datetime, timedelta

    return MeetingTokenClaims(
        user_id=uuid4(),
        workspace_id=uuid4(),
        decision_id=uuid4(),
        display_name="Raman Singh",
        role=role,
        can_facilitate=can_facilitate,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


async def test_non_facilitator_cannot_start_timer() -> None:
    repository = AsyncMock(spec=MeetingRoomRepository)
    user_claims = claims(can_facilitate=False)
    event = MeetingClientEvent.model_validate(
        {"type": "timer.start", "payload": {"duration_seconds": 60}}
    )
    await _handle_client_event(event, user_claims, repository)
    repository.start_timer.assert_not_awaited()
    published = repository.publish.await_args.args[0]
    assert published["payload"] == {"code": "facilitator_required"}
    assert published["target_user_id"] == str(user_claims.user_id)


async def test_facilitator_can_sync_voting_state() -> None:
    repository = AsyncMock(spec=MeetingRoomRepository)
    facilitator = claims(can_facilitate=True, role="admin")
    session_id = uuid4()
    event = MeetingClientEvent.model_validate(
        {
            "type": "vote.sync",
            "payload": {"session_id": str(session_id), "status": "open"},
        }
    )
    await _handle_client_event(event, facilitator, repository)
    published = repository.publish.await_args.args[0]
    assert published["type"] == "vote.synced"
    assert published["payload"]["session_id"] == str(session_id)


async def test_viewer_cannot_enter_speaking_queue() -> None:
    repository = AsyncMock(spec=MeetingRoomRepository)
    viewer = claims(can_facilitate=False, role="viewer")
    event = MeetingClientEvent.model_validate({"type": "speaker.join"})
    await _handle_client_event(event, viewer, repository)
    repository.join_speaking_queue.assert_not_awaited()
