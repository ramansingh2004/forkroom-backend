from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hasher = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_token_expires_in: int


def hash_password(password: str) -> str:
    """Hash a password with Argon2 using pwdlib's recommended settings."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches its stored hash."""
    return password_hasher.verify(password, password_hash)


def _create_token(
    *,
    subject: UUID,
    token_type: str,
    secret: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def create_token_pair(user_id: UUID) -> TokenPair:
    """Create independently signed access and refresh JWTs for a user."""
    settings = get_settings()
    access_lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_lifetime = timedelta(days=settings.refresh_token_expire_days)

    return TokenPair(
        access_token=_create_token(
            subject=user_id,
            token_type="access",
            secret=settings.jwt_access_secret,
            expires_delta=access_lifetime,
        ),
        refresh_token=_create_token(
            subject=user_id,
            token_type="refresh",
            secret=settings.jwt_refresh_secret,
            expires_delta=refresh_lifetime,
        ),
        access_token_expires_in=int(access_lifetime.total_seconds()),
    )
