from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis


class RefreshTokenRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def consume(
        self,
        jti: UUID,
        expires_at: datetime,
    ) -> bool:
        """Atomically mark a refresh token as used until its expiry time."""
        ttl = max( # It tells Redis how long the key should remain stored.
            1,
            int((expires_at - datetime.now(UTC)).total_seconds()),
        )

        result = await self._redis.set(
            f"auth:refresh:used:{jti}",
            "1",
            ex=ttl,
            nx=True,
        )

        return bool(result)
