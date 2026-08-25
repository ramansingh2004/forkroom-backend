import json
import secrets
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from typing import cast

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class AuthOAuthState:
    code_verifier: str
    return_path: str


class AuthOAuthStateRepository:
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

    async def issue(self, value: AuthOAuthState, ttl_seconds: int) -> str:
        state = secrets.token_urlsafe(32)
        await self._redis.set(
            f"auth:google:oauth-state:{state}",
            json.dumps(asdict(value), separators=(",", ":")),
            ex=ttl_seconds,
        )
        return state

    async def consume(self, state: str) -> AuthOAuthState | None:
        pending_result = cast(
            Awaitable[object],
            self._redis.eval(
                self._CONSUME_SCRIPT,
                1,
                f"auth:google:oauth-state:{state}",
            ),
        )
        result = await pending_result
        if result is None or result is False:
            return None
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        try:
            payload = cast(dict[str, object], json.loads(cast(str, result)))
            return AuthOAuthState(
                code_verifier=cast(str, payload["code_verifier"]),
                return_path=cast(str, payload["return_path"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
