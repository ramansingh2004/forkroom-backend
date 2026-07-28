from dataclasses import dataclass
from datetime import timedelta

from app.core.config import get_settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InactiveAccountError,
    InvalidActionTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import (
    TokenPair,
    create_token_pair,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.integrations.email import EmailService
from app.models.user import User
from app.repositories.action_token import ActionTokenRepository
from app.repositories.refresh_token import (
    RefreshTokenRepository,
)
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ActionTokenRequest,
    EmailVerificationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: TokenPair


class AuthService:
    _EMAIL_VERIFICATION_PURPOSE = "email-verification"
    _PASSWORD_RESET_PURPOSE = "password-reset"

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        action_tokens: ActionTokenRepository,
        email_service: EmailService,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_tokens
        self._action_tokens = action_tokens
        self._email = email_service

    @staticmethod
    def _family_revocation_ttl() -> int:
        return int(timedelta(days=(get_settings().refresh_token_expire_days)).total_seconds())

    async def register(
        self,
        payload: RegisterRequest,
    ) -> User:
        normalized_email = payload.email.lower()

        if await self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyRegisteredError

        user = User(
            email=normalized_email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )

        created_user = await self._users.create(user)
        await self._send_verification_email(created_user)
        return created_user

    async def login(
        self,
        payload: LoginRequest,
    ) -> LoginResult:
        user = await self._users.get_by_email(payload.email.lower())

        if user is None or not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise InvalidCredentialsError

        if not user.is_active:
            raise InactiveAccountError

        if not user.is_email_verified:
            raise EmailNotVerifiedError

        return LoginResult(
            user=user,
            tokens=create_token_pair(
                user.id,
                token_version=user.auth_version or 0,
            ),
        )

    async def refresh(
        self,
        payload: RefreshRequest,
    ) -> TokenPair:
        decoded = decode_refresh_token(payload.refresh_token)

        if await self._refresh_tokens.is_family_revoked(decoded.family_id):
            raise InvalidTokenError

        was_consumed = await self._refresh_tokens.consume(
            decoded.jti,
            decoded.expires_at,
        )

        if not was_consumed:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InvalidTokenError

        user = await self._users.get_by_id(decoded.user_id)

        if user is None:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InvalidTokenError

        if not user.is_active:
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InactiveAccountError

        if decoded.token_version != (user.auth_version or 0):
            await self._refresh_tokens.revoke_family(
                decoded.family_id,
                self._family_revocation_ttl(),
            )
            raise InvalidTokenError

        return create_token_pair(
            user.id,
            decoded.family_id,
            user.auth_version or 0,
        )

    async def logout(
        self,
        payload: LogoutRequest,
    ) -> None:
        decoded = decode_refresh_token(payload.refresh_token)

        await self._refresh_tokens.revoke_family(
            decoded.family_id,
            self._family_revocation_ttl(),
        )

    async def request_email_verification(
        self,
        payload: EmailVerificationRequest,
    ) -> None:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None or not user.is_active or user.is_email_verified:
            return
        await self._send_verification_email(user)

    async def verify_email(self, payload: ActionTokenRequest) -> User:
        user_id = await self._action_tokens.consume(
            self._EMAIL_VERIFICATION_PURPOSE,
            payload.token,
        )
        if user_id is None:
            raise InvalidActionTokenError

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidActionTokenError
        if not user.is_active:
            raise InactiveAccountError
        if not user.is_email_verified:
            user = await self._users.mark_email_verified(user)
        return user

    async def forgot_password(self, payload: ForgotPasswordRequest) -> None:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None or not user.is_active:
            return

        settings = get_settings()
        token = await self._action_tokens.issue(
            self._PASSWORD_RESET_PURPOSE,
            user.id,
            settings.password_reset_expire_minutes * 60,
        )
        await self._email.send_password_reset_email(
            user.email,
            user.display_name,
            token,
        )

    async def reset_password(self, payload: ResetPasswordRequest) -> None:
        user_id = await self._action_tokens.consume(
            self._PASSWORD_RESET_PURPOSE,
            payload.token,
        )
        if user_id is None:
            raise InvalidActionTokenError

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidActionTokenError
        if not user.is_active:
            raise InactiveAccountError

        await self._users.update_password(
            user,
            hash_password(payload.new_password),
        )

    async def _send_verification_email(self, user: User) -> None:
        settings = get_settings()
        token = await self._action_tokens.issue(
            self._EMAIL_VERIFICATION_PURPOSE,
            user.id,
            settings.email_verification_expire_minutes * 60,
        )
        await self._email.send_verification_email(
            user.email,
            user.display_name,
            token,
        )
