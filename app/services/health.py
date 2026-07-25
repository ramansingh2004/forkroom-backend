import asyncio
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database(session: AsyncSession) -> str:
    try:
        await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"


async def check_redis(redis: Redis) -> str:
    try:
        ping_result = await cast(Awaitable[bool], redis.ping())
        return "ok" if ping_result else "unavailable"
    except Exception:
        return "unavailable"


async def check_dependencies(session: AsyncSession, redis: Redis) -> dict[str, str]:
    database_status, redis_status = await asyncio.gather(
        check_database(session),
        check_redis(redis),
    )
    return {
        "database": database_status,
        "redis": redis_status,
    }
