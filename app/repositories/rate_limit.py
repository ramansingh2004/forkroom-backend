from collections.abc import Awaitable
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


class RateLimitRepository:
    _HIT_SCRIPT = """
    local current = redis.call("INCR", KEYS[1])
    if current == 1 then
        redis.call("EXPIRE", KEYS[1], ARGV[1])
    end
    local ttl = redis.call("TTL", KEYS[1])
    return {current, ttl}
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        pending_result = cast(
            Awaitable[object],
            self._redis.eval(
                self._HIT_SCRIPT,
                1,
                key,
                window_seconds,
            ),
        )

        values = cast(
            list[int],
            await pending_result,
        )

        count, ttl = (int(value) for value in values)

        return RateLimitResult(
            allowed=count <= limit,
            retry_after=max(ttl, 1),
        )
