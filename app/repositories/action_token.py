import hashlib
import secrets
from collections.abc import Awaitable
from typing import cast
from uuid import UUID

from redis.asyncio import Redis


class ActionTokenRepository:
    _CONSUME_SCRIPT = """
    local user_id = redis.call("GET", KEYS[1])
    if not user_id then
        return false
    end
    redis.call("DEL", KEYS[1])
    local current_digest = redis.call("GET", KEYS[2] .. user_id)
    if current_digest == ARGV[1] then
        redis.call("DEL", KEYS[2] .. user_id)
    end
    return user_id
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def issue(
        self,
        purpose: str,
        user_id: UUID,
        ttl_seconds: int,
    ) -> str:
        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        user_key = f"auth:action:{purpose}:user:{user_id}"
        previous_digest = await self._redis.get(user_key)

        if previous_digest is not None:
            if isinstance(previous_digest, bytes):
                previous_digest = previous_digest.decode("utf-8")
            await self._redis.delete(f"auth:action:{purpose}:token:{previous_digest}")

        await self._redis.set(
            f"auth:action:{purpose}:token:{digest}",
            str(user_id),
            ex=ttl_seconds,
        )
        await self._redis.set(user_key, digest, ex=ttl_seconds)
        return token

    async def consume(self, purpose: str, token: str) -> UUID | None:
        digest = self._digest(token)
        pending_result = cast(
            Awaitable[object],
            self._redis.eval(
                self._CONSUME_SCRIPT,
                2,
                f"auth:action:{purpose}:token:{digest}",
                f"auth:action:{purpose}:user:",
                digest,
            ),
        )
        result = await pending_result

        if result is None or result is False:
            return None
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        return UUID(cast(str, result))
