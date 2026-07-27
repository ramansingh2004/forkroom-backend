from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.exceptions import InvalidTokenError
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.rate_limit import (
    RateLimitRepository,
)
from app.repositories.refresh_token import (
    RefreshTokenRepository,
)
from app.repositories.user import UserRepository
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    redis: Annotated[
        Redis,
        Depends(get_redis),
    ],
) -> AuthService:
    return AuthService(
        UserRepository(session),
        RefreshTokenRepository(redis),
    )


async def enforce_auth_rate_limit(
    request: Request,
    redis: Annotated[
        Redis,
        Depends(get_redis),
    ],
) -> None:
    settings = get_settings()
    action = request.url.path.rsplit(
        "/",
        maxsplit=1,
    )[-1]

    limits = {
        "register": (settings.register_rate_limit_requests),
        "login": (settings.login_rate_limit_requests),
        "refresh": (settings.refresh_rate_limit_requests),
        "logout": (settings.logout_rate_limit_requests),
    }

    limit = limits.get(action)

    if limit is None:
        return

    client_ip = request.client.host if request.client is not None else "unknown"

    result = await RateLimitRepository(redis).hit(
        key=f"auth:rate:{action}:{client_ip}",
        limit=limit,
        window_seconds=(settings.auth_rate_limit_window_seconds),
    )

    if not result.allowed:
        raise HTTPException(
            status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
            detail=("Too many authentication requests"),
            headers={"Retry-After": str(result.retry_after)},
        )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    redis: Annotated[
        Redis,
        Depends(get_redis),
    ],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=("Invalid or expired access token"),
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        decoded = decode_access_token(credentials.credentials)
    except InvalidTokenError as error:
        raise unauthorized from error

    is_revoked = await RefreshTokenRepository(redis).is_family_revoked(decoded.family_id)

    if is_revoked:
        raise unauthorized

    user = await UserRepository(session).get_by_id(decoded.user_id)

    if user is None:
        raise unauthorized

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        )

    return user
