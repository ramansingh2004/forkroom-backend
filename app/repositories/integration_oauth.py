import json
import secrets
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from typing import cast
from uuid import UUID

from redis.asyncio import Redis

from app.models.integration import IntegrationProvider


@dataclass(frozen=True, slots=True)
class IntegrationOAuthState:
    workspace_id: UUID
    user_id: UUID
    provider: IntegrationProvider
    code_verifier: str
    return_path: str


class IntegrationOAuthStateRepository:
    _CONSUME_SCRIPT = """
    local value = redis.call("GET", KEYS[1])
    if not value then
        return false
    end
    redis.call("DEL", KEYS[1])
    return value
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def issue(self, value: IntegrationOAuthState, ttl_seconds: int) -> str:
        state = secrets.token_urlsafe(32)
        payload = asdict(value)
        payload["workspace_id"] = str(value.workspace_id)
        payload["user_id"] = str(value.user_id)
        payload["provider"] = value.provider.value
        await self._redis.set(
            f"integration:oauth-state:{state}",
            json.dumps(payload, separators=(",", ":")),
            ex=ttl_seconds,
        )
        return state

    async def consume(self, state: str) -> IntegrationOAuthState | None:
        pending_result = cast(
            Awaitable[object],
            self._redis.eval(
                self._CONSUME_SCRIPT,
                1,
                f"integration:oauth-state:{state}",
            ),
        )
        result = await pending_result
        if result is None or result is False:
            return None
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        try:
            payload = cast(dict[str, object], json.loads(cast(str, result)))
            return IntegrationOAuthState(
                workspace_id=UUID(cast(str, payload["workspace_id"])),
                user_id=UUID(cast(str, payload["user_id"])),
                provider=IntegrationProvider(cast(str, payload["provider"])),
                code_verifier=cast(str, payload["code_verifier"]),
                return_path=cast(str, payload["return_path"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
