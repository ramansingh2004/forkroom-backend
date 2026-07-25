from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import ReadinessResponse
from app.services.health import check_dependencies


async def get_readiness(session: AsyncSession, redis: Redis) -> ReadinessResponse:
    checks = await check_dependencies(session=session, redis=redis)
    overall_status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return ReadinessResponse(status=overall_status, checks=checks)
