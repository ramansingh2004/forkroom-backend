from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.meeting import MeetingClientEvent


def test_signaling_event_requires_target() -> None:
    with pytest.raises(ValidationError):
        MeetingClientEvent.model_validate({"type": "signal.offer", "payload": {"sdp": "v=0"}})


def test_targeted_ice_event_is_valid() -> None:
    target = uuid4()
    event = MeetingClientEvent.model_validate(
        {
            "type": "signal.ice",
            "target_user_id": str(target),
            "payload": {"candidate": "candidate:1"},
        }
    )
    assert event.target_user_id == target


def test_timer_requires_integer_duration() -> None:
    with pytest.raises(ValidationError):
        MeetingClientEvent.model_validate(
            {"type": "timer.start", "payload": {"duration_seconds": "60"}}
        )
