from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MeetingPermission(StrEnum):
    FACILITATE = "facilitate"
    PARTICIPATE = "participate"
    OBSERVE = "observe"


class IceServer(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class MeetingTokenResponse(BaseModel):
    token: str
    expires_in: int
    expires_at: datetime
    websocket_url: str
    permission: MeetingPermission
    max_participants: int
    ice_servers: list[IceServer]


class MeetingEventType(StrEnum):
    HEARTBEAT = "heartbeat"
    SIGNAL_OFFER = "signal.offer"
    SIGNAL_ANSWER = "signal.answer"
    SIGNAL_ICE = "signal.ice"
    MEDIA_STATE = "media.state"
    SPEAKER_JOIN = "speaker.join"
    SPEAKER_LEAVE = "speaker.leave"
    TIMER_START = "timer.start"
    TIMER_CANCEL = "timer.cancel"
    VOTE_SYNC = "vote.sync"


class MeetingClientEvent(BaseModel):
    type: MeetingEventType
    target_user_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_event_shape(self) -> "MeetingClientEvent":
        if (
            self.type
            in {
                MeetingEventType.SIGNAL_OFFER,
                MeetingEventType.SIGNAL_ANSWER,
                MeetingEventType.SIGNAL_ICE,
            }
            and self.target_user_id is None
        ):
            raise ValueError("Signaling events require target_user_id")
        if self.type is MeetingEventType.TIMER_START:
            duration = self.payload.get("duration_seconds")
            if not isinstance(duration, int) or isinstance(duration, bool):
                raise ValueError("Timer start requires an integer duration_seconds")
        return self


class MeetingParticipant(BaseModel):
    user_id: UUID
    display_name: str
    role: str
    can_facilitate: bool
    joined_at: datetime


class MeetingTimer(BaseModel):
    started_by: UUID
    started_at: datetime
    ends_at: datetime


class MeetingState(BaseModel):
    participants: list[MeetingParticipant]
    speaking_queue: list[UUID]
    timer: MeetingTimer | None = None
