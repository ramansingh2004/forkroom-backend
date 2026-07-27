from unittest.mock import AsyncMock

from app.repositories.rate_limit import (
    RateLimitRepository,
)


async def test_rate_limit_allows_request_within_limit() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [3, 42]
    repository = RateLimitRepository(redis)

    result = await repository.hit(
        key="auth:rate:login:127.0.0.1",
        limit=5,
        window_seconds=60,
    )

    assert result.allowed is True
    assert result.retry_after == 42


async def test_rate_limit_rejects_request_above_limit() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [6, 37]
    repository = RateLimitRepository(redis)

    result = await repository.hit(
        key="auth:rate:login:127.0.0.1",
        limit=5,
        window_seconds=60,
    )

    assert result.allowed is False
    assert result.retry_after == 37
