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
        ttl = max(
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

    async def is_family_revoked(
        self,
        family_id: UUID,
    ) -> bool:
        key = f"auth:refresh:family:revoked:{family_id}"
        return bool(await self._redis.exists(key))

    async def revoke_family(
        self,
        family_id: UUID,
        ttl_seconds: int,
    ) -> None:
        await self._redis.set(
            (f"auth:refresh:family:revoked:{family_id}"),
            "1",
            ex=ttl_seconds,
        )
