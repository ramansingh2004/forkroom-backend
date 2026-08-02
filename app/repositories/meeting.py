import json
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.exceptions import MeetingRoomFullError
from app.core.security import MeetingTokenClaims
from app.schemas.meeting import MeetingParticipant, MeetingState, MeetingTimer


async def _redis_result[T](value: Awaitable[T] | T) -> T:
    return await cast(Awaitable[T], value)


class MeetingRoomRepository:
    """Redis-backed ephemeral meeting state shared by every API replica."""

    def __init__(self, redis: Redis, workspace_id: UUID, decision_id: UUID) -> None:
        self._redis = redis
        self._prefix = f"meeting:{workspace_id}:{decision_id}"
        self.channel = f"{self._prefix}:events"
        self._participants = f"{self._prefix}:participants"
        self._presence = f"{self._prefix}:presence"
        self._speakers = f"{self._prefix}:speakers"
        self._timer = f"{self._prefix}:timer"
        self._join_lock = f"{self._prefix}:join-lock"

    async def _prune_stale(self) -> None:
        now = datetime.now(UTC).timestamp()
        stale = await self._redis.zrangebyscore(self._presence, min="-inf", max=now)
        if not stale:
            return
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.zrem(self._presence, *stale)
        pipeline.hdel(self._participants, *stale)
        for user_id in stale:
            pipeline.lrem(self._speakers, 0, user_id)
        await pipeline.execute()

    async def join(self, claims: MeetingTokenClaims) -> MeetingState:
        settings = get_settings()
        lock = self._redis.lock(self._join_lock, timeout=5, blocking_timeout=3)
        acquired = await lock.acquire()
        if not acquired:
            raise MeetingRoomFullError
        try:
            await self._prune_stale()
            user_key = str(claims.user_id)
            existing = await _redis_result(self._redis.hexists(self._participants, user_key))
            participant_count = await _redis_result(self._redis.hlen(self._participants))
            if not existing and participant_count >= settings.meeting_max_participants:
                raise MeetingRoomFullError
            now = datetime.now(UTC)
            participant = MeetingParticipant(
                user_id=claims.user_id,
                display_name=claims.display_name,
                role=claims.role,
                can_facilitate=claims.can_facilitate,
                joined_at=now,
            )
            expires_at = now.timestamp() + settings.meeting_presence_ttl_seconds
            pipeline = self._redis.pipeline(transaction=True)
            pipeline.hset(self._participants, user_key, participant.model_dump_json())
            pipeline.zadd(self._presence, {user_key: expires_at})
            for key in (self._participants, self._presence, self._speakers, self._timer):
                pipeline.expire(key, settings.meeting_presence_ttl_seconds * 3)
            await pipeline.execute()
        finally:
            await lock.release()
        return await self.snapshot()

    async def touch(self, user_id: UUID) -> None:
        settings = get_settings()
        expires_at = datetime.now(UTC).timestamp() + settings.meeting_presence_ttl_seconds
        await self._redis.zadd(self._presence, {str(user_id): expires_at})

    async def leave(self, user_id: UUID) -> None:
        user_key = str(user_id)
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.hdel(self._participants, user_key)
        pipeline.zrem(self._presence, user_key)
        pipeline.lrem(self._speakers, 0, user_key)
        await pipeline.execute()

    async def join_speaking_queue(self, user_id: UUID) -> list[UUID]:
        user_key = str(user_id)
        if await _redis_result(self._redis.lpos(self._speakers, user_key)) is None:
            await _redis_result(self._redis.rpush(self._speakers, user_key))
        return await self.speaking_queue()

    async def leave_speaking_queue(self, user_id: UUID) -> list[UUID]:
        await _redis_result(self._redis.lrem(self._speakers, 0, str(user_id)))
        return await self.speaking_queue()

    async def speaking_queue(self) -> list[UUID]:
        values = await _redis_result(self._redis.lrange(self._speakers, 0, -1))
        return [UUID(value) for value in values]

    async def start_timer(self, user_id: UUID, duration_seconds: int) -> MeetingTimer:
        now = datetime.now(UTC)
        timer = MeetingTimer(
            started_by=user_id,
            started_at=now,
            ends_at=now + timedelta(seconds=duration_seconds),
        )
        await self._redis.set(
            self._timer,
            timer.model_dump_json(),
            ex=duration_seconds + get_settings().meeting_presence_ttl_seconds,
        )
        return timer

    async def cancel_timer(self) -> None:
        await self._redis.delete(self._timer)

    async def snapshot(self) -> MeetingState:
        await self._prune_stale()
        raw_participants = await _redis_result(self._redis.hgetall(self._participants))
        participants = sorted(
            (MeetingParticipant.model_validate_json(value) for value in raw_participants.values()),
            key=lambda participant: participant.joined_at,
        )
        raw_timer = await self._redis.get(self._timer)
        timer = MeetingTimer.model_validate_json(raw_timer) if raw_timer else None
        if timer is not None and timer.ends_at <= datetime.now(UTC):
            await self.cancel_timer()
            timer = None
        return MeetingState(
            participants=participants,
            speaking_queue=await self.speaking_queue(),
            timer=timer,
        )

    async def publish(self, event: dict[str, object]) -> None:
        await self._redis.publish(self.channel, json.dumps(event, separators=(",", ":")))

    async def allow_event(self, user_id: UUID) -> bool:
        """Allow at most 60 client events per rolling ten-second bucket."""
        bucket = int(datetime.now(UTC).timestamp()) // 10
        key = f"{self._prefix}:rate:{user_id}:{bucket}"
        count = int(await _redis_result(self._redis.incr(key)))
        if count == 1:
            await self._redis.expire(key, 12)
        return bool(count <= 60)
