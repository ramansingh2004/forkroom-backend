from unittest.mock import AsyncMock
from uuid import uuid4

from app.repositories.action_token import ActionTokenRepository


async def test_issue_action_token_stores_only_digest() -> None:
    redis = AsyncMock()
    redis.get.return_value = None
    repository = ActionTokenRepository(redis)
    user_id = uuid4()

    token = await repository.issue(
        "password-reset",
        user_id,
        ttl_seconds=900,
    )

    assert len(token) >= 32
    assert token not in str(redis.set.await_args_list)
    assert str(user_id) in str(redis.set.await_args_list)


async def test_consume_action_token_returns_user_id() -> None:
    redis = AsyncMock()
    user_id = uuid4()
    redis.eval.return_value = str(user_id).encode()
    repository = ActionTokenRepository(redis)

    result = await repository.consume(
        "email-verification",
        "verification-token",
    )

    assert result == user_id


async def test_consume_action_token_rejects_missing_token() -> None:
    redis = AsyncMock()
    redis.eval.return_value = None
    repository = ActionTokenRepository(redis)

    result = await repository.consume(
        "password-reset",
        "expired-token",
    )

    assert result is None
