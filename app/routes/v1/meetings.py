import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis

from app.controllers.meeting import execute_meeting_action
from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError, MeetingRoomFullError
from app.core.redis import get_redis_client
from app.core.security import MeetingTokenClaims, decode_meeting_token
from app.dependencies.auth import get_current_user
from app.dependencies.meeting import get_meeting_service
from app.models.user import User
from app.repositories.meeting import MeetingRoomRepository
from app.schemas.meeting import MeetingClientEvent, MeetingEventType, MeetingTokenResponse
from app.services.meeting import MeetingService

router = APIRouter(tags=["Live meetings"])

CurrentUser = Annotated[User, Depends(get_current_user)]
MeetingServiceDependency = Annotated[MeetingService, Depends(get_meeting_service)]


@router.post(
    "/workspaces/{workspace_id}/decisions/{decision_id}/meeting-token",
    response_model=MeetingTokenResponse,
    summary="Issue a short-lived decision-meeting token and TURN credentials",
)
async def issue_meeting_token(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: MeetingServiceDependency,
) -> MeetingTokenResponse:
    return await execute_meeting_action(
        lambda: service.issue_token(current_user, workspace_id, decision_id)
    )


def _event_envelope(
    event_type: str,
    claims: MeetingTokenClaims,
    *,
    payload: dict[str, object] | None = None,
    target_user_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "type": event_type,
        "sender": {
            "user_id": str(claims.user_id),
            "display_name": claims.display_name,
            "role": claims.role,
        },
        "target_user_id": str(target_user_id) if target_user_id else None,
        "payload": payload or {},
        "occurred_at": datetime.now(UTC).isoformat(),
    }


async def _relay_events(
    websocket: WebSocket,
    redis: Redis,
    repository: MeetingRoomRepository,
    user_id: UUID,
    send_lock: asyncio.Lock,
) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(repository.channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            event = json.loads(message["data"])
            target = event.get("target_user_id")
            if target is not None and target != str(user_id):
                continue
            async with send_lock:
                await websocket.send_json(event)
    finally:
        await pubsub.unsubscribe(repository.channel)
        await pubsub.close()


async def _handle_client_event(
    event: MeetingClientEvent,
    claims: MeetingTokenClaims,
    repository: MeetingRoomRepository,
) -> None:
    settings = get_settings()
    if event.type is MeetingEventType.HEARTBEAT:
        await repository.touch(claims.user_id)
        return

    if event.type in {
        MeetingEventType.SIGNAL_OFFER,
        MeetingEventType.SIGNAL_ANSWER,
        MeetingEventType.SIGNAL_ICE,
        MeetingEventType.MEDIA_STATE,
    }:
        await repository.publish(
            _event_envelope(
                event.type.value,
                claims,
                payload=event.payload,
                target_user_id=event.target_user_id,
            )
        )
        return

    if event.type is MeetingEventType.SPEAKER_JOIN:
        if claims.role == "viewer":
            return
        queue = await repository.join_speaking_queue(claims.user_id)
        await repository.publish(
            _event_envelope(
                "speaker.queue",
                claims,
                payload={"user_ids": [str(user_id) for user_id in queue]},
            )
        )
        return

    if event.type is MeetingEventType.SPEAKER_LEAVE:
        queue = await repository.leave_speaking_queue(claims.user_id)
        await repository.publish(
            _event_envelope(
                "speaker.queue",
                claims,
                payload={"user_ids": [str(user_id) for user_id in queue]},
            )
        )
        return

    if not claims.can_facilitate:
        await repository.publish(
            _event_envelope(
                "meeting.error",
                claims,
                payload={"code": "facilitator_required"},
                target_user_id=claims.user_id,
            )
        )
        return

    if event.type is MeetingEventType.TIMER_START:
        duration = int(event.payload["duration_seconds"])
        if duration < 1 or duration > settings.meeting_max_timer_seconds:
            await repository.publish(
                _event_envelope(
                    "meeting.error",
                    claims,
                    payload={"code": "invalid_timer_duration"},
                    target_user_id=claims.user_id,
                )
            )
            return
        timer = await repository.start_timer(claims.user_id, duration)
        await repository.publish(
            _event_envelope("timer.started", claims, payload=timer.model_dump(mode="json"))
        )
    elif event.type is MeetingEventType.TIMER_CANCEL:
        await repository.cancel_timer()
        await repository.publish(_event_envelope("timer.cancelled", claims))
    elif event.type is MeetingEventType.VOTE_SYNC:
        await repository.publish(_event_envelope("vote.synced", claims, payload=event.payload))


@router.websocket("/ws/meetings/{workspace_id}/{decision_id}")
async def decision_meeting_websocket(
    websocket: WebSocket,
    workspace_id: UUID,
    decision_id: UUID,
    token: Annotated[str, Query(min_length=20)],
) -> None:
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin not in settings.meeting_allowed_origins:
        await websocket.close(code=4403, reason="Origin not allowed")
        return
    try:
        claims = decode_meeting_token(token)
    except InvalidTokenError:
        await websocket.close(code=4401, reason="Invalid or expired meeting token")
        return
    if claims.workspace_id != workspace_id or claims.decision_id != decision_id:
        await websocket.close(code=4403, reason="Meeting token scope mismatch")
        return

    redis = get_redis_client()
    repository = MeetingRoomRepository(redis, workspace_id, decision_id)
    try:
        state = await repository.join(claims)
    except MeetingRoomFullError:
        await websocket.close(code=4409, reason="Meeting room is full")
        return

    await websocket.accept()
    send_lock = asyncio.Lock()
    async with send_lock:
        await websocket.send_json(
            _event_envelope(
                "meeting.ready",
                claims,
                payload=state.model_dump(mode="json"),
                target_user_id=claims.user_id,
            )
        )
    relay_task = asyncio.create_task(
        _relay_events(websocket, redis, repository, claims.user_id, send_lock)
    )
    await repository.publish(_event_envelope("presence.joined", claims))
    try:
        while True:
            raw: Any = await websocket.receive_json()
            if len(json.dumps(raw)) > 65_536:
                await websocket.close(code=4400, reason="Meeting event is too large")
                break
            if not await repository.allow_event(claims.user_id):
                await websocket.close(code=4429, reason="Meeting event rate limit exceeded")
                break
            try:
                event = MeetingClientEvent.model_validate(raw)
            except ValidationError:
                await repository.publish(
                    _event_envelope(
                        "meeting.error",
                        claims,
                        payload={"code": "invalid_event"},
                        target_user_id=claims.user_id,
                    )
                )
                continue
            await _handle_client_event(event, claims, repository)
    except WebSocketDisconnect:
        pass
    finally:
        relay_task.cancel()
        with suppress(asyncio.CancelledError):
            await relay_task
        await repository.leave(claims.user_id)
        await repository.publish(_event_envelope("presence.left", claims))
