from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError

password_hasher = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_token_expires_in: int


@dataclass(frozen=True, slots=True)
class DecodedToken:
    user_id: UUID
    jti: UUID
    family_id: UUID
    token_version: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CollaborationToken:
    token: str
    expires_in: int
    expires_at: datetime


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
    family_id: UUID,
    token_version: int,
    secret: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": str(uuid4()),
        "family": str(family_id),
        "ver": token_version,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        secret,
        algorithm=JWT_ALGORITHM,
    )


def create_token_pair(
    user_id: UUID,
    family_id: UUID | None = None,
    token_version: int = 0,
) -> TokenPair:
    """Create independently signed access and refresh JWTs for a user."""
    settings = get_settings()
    token_family_id = family_id or uuid4()

    access_lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_lifetime = timedelta(days=settings.refresh_token_expire_days)

    return TokenPair(
        access_token=_create_token(
            subject=user_id,
            token_type="access",
            family_id=token_family_id,
            token_version=token_version,
            secret=settings.jwt_access_secret,
            expires_delta=access_lifetime,
        ),
        refresh_token=_create_token(
            subject=user_id,
            token_type="refresh",
            family_id=token_family_id,
            token_version=token_version,
            secret=settings.jwt_refresh_secret,
            expires_delta=refresh_lifetime,
        ),
        access_token_expires_in=int(access_lifetime.total_seconds()),
    )


def _decode_token(
    *,
    token: str,
    expected_type: str,
    secret: str,
) -> DecodedToken:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": [
                    "sub",
                    "type",
                    "jti",
                    "family",
                    "ver",
                    "iat",
                    "exp",
                ]
            },
        )

        if payload["type"] != expected_type:
            raise jwt.InvalidTokenError

        return DecodedToken(
            user_id=UUID(payload["sub"]),
            jti=UUID(payload["jti"]),
            family_id=UUID(payload["family"]),
            token_version=int(payload["ver"]),
            expires_at=datetime.fromtimestamp(
                payload["exp"],
                tz=UTC,
            ),
        )

    except (
        jwt.InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidTokenError from error


def decode_access_token(token: str) -> DecodedToken:
    """Validate and decode an access token."""
    return _decode_token(
        token=token,
        expected_type="access",
        secret=get_settings().jwt_access_secret,
    )


def decode_refresh_token(token: str) -> DecodedToken:
    """Validate and decode a refresh token."""
    return _decode_token(
        token=token,
        expected_type="refresh",
        secret=get_settings().jwt_refresh_secret,
    )


def create_collaboration_token(
    *,
    user_id: UUID,
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    document_name: str,
    permission: str,
    display_name: str,
) -> CollaborationToken:
    """Create a short-lived, document-scoped token for Hocuspocus."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.collaboration_token_expire_minutes)
    expires_at = now + expires_delta
    payload = {
        "sub": str(user_id),
        "type": "collaboration",
        "jti": str(uuid4()),
        "iss": "forkroom-api",
        "aud": "forkroom-collaboration",
        "workspace_id": str(workspace_id),
        "decision_id": str(decision_id),
        "proposal_id": str(proposal_id),
        "document_name": document_name,
        "permission": permission,
        "display_name": display_name,
        "iat": now,
        "exp": expires_at,
    }
    return CollaborationToken(
        token=jwt.encode(payload, settings.jwt_collaboration_secret, algorithm=JWT_ALGORITHM),
        expires_in=int(expires_delta.total_seconds()),
        expires_at=expires_at,
    )
