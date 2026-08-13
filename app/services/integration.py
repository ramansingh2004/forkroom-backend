import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import (
    IntegrationAccessDeniedError,
    IntegrationConfigurationError,
    IntegrationNotFoundError,
    IntegrationOAuthStateError,
    IntegrationProviderError,
    IntegrationProviderUnavailableError,
    WorkspaceNotFoundError,
)
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.integrations.providers.base import IntegrationProviderClient, ProviderDestination
from app.integrations.token_encryption import IntegrationTokenCipher
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationDelivery,
    IntegrationEventType,
    IntegrationProvider,
    IntegrationSubscription,
)
from app.models.user import User
from app.permissions.workspace import can_manage_workspace
from app.repositories.integration import IntegrationRepository, SubscriptionConfiguration
from app.repositories.integration_oauth import (
    IntegrationOAuthState,
    IntegrationOAuthStateRepository,
)
from app.repositories.workspace import WorkspaceRepository
from app.schemas.integration import IntegrationSubscriptionUpdate


class IntegrationService:
    supported_events = (
        IntegrationEventType.DECISION_ACTIVATED,
        IntegrationEventType.VOTING_OPENED,
        IntegrationEventType.VOTING_CLOSED,
        IntegrationEventType.DECISION_LOCKED,
    )

    def __init__(
        self,
        repository: IntegrationRepository,
        workspace_repository: WorkspaceRepository,
        oauth_states: IntegrationOAuthStateRepository,
        providers: IntegrationProviderRegistry,
        settings: Settings,
    ) -> None:
        self._integrations = repository
        self._workspaces = workspace_repository
        self._oauth_states = oauth_states
        self._providers = providers
        self._settings = settings

    def list_providers(self) -> list[IntegrationProviderClient]:
        encryption_configured = bool(self._settings.integration_token_encryption_key)
        return [
            provider
            for provider in self._providers.list()
            if provider.available and encryption_configured
        ]

    def provider_catalog(self) -> list[tuple[IntegrationProviderClient, bool]]:
        encryption_configured = bool(self._settings.integration_token_encryption_key)
        return [
            (provider, provider.available and encryption_configured)
            for provider in self._providers.list()
        ]

    async def list_connections(
        self,
        current_user: User,
        workspace_id: UUID,
    ) -> list[IntegrationConnection]:
        await self._require_membership(current_user.id, workspace_id)
        return await self._integrations.list_connections(workspace_id)

    async def get_connection(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> IntegrationConnection:
        await self._require_membership(current_user.id, workspace_id)
        return await self._require_connection(workspace_id, connection_id)

    async def authorize(
        self,
        current_user: User,
        workspace_id: UUID,
        provider_name: IntegrationProvider,
        return_path: str | None,
    ) -> tuple[str, datetime]:
        await self._require_manager(current_user.id, workspace_id)
        self._cipher()
        provider = self._providers.get(provider_name)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        safe_return_path = return_path or f"/w/{workspace_id}/integrations"
        state = await self._oauth_states.issue(
            IntegrationOAuthState(
                workspace_id=workspace_id,
                user_id=current_user.id,
                provider=provider_name,
                code_verifier=code_verifier,
                return_path=safe_return_path,
            ),
            self._settings.integration_oauth_state_ttl_seconds,
        )
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.integration_oauth_state_ttl_seconds
        )
        return provider.build_authorization_url(
            state=state,
            code_challenge=code_challenge,
        ), expires_at

    async def complete_authorization(
        self,
        provider_name: IntegrationProvider,
        *,
        state: str | None,
        code: str | None,
        provider_error: str | None,
    ) -> str:
        if not state:
            raise IntegrationOAuthStateError
        oauth_state = await self._oauth_states.consume(state)
        if oauth_state is None or oauth_state.provider is not provider_name:
            raise IntegrationOAuthStateError
        if provider_error or not code:
            reason = "access_denied" if provider_error == "access_denied" else "oauth_failed"
            return self._callback_redirect(oauth_state.return_path, error=reason)
        try:
            await self._require_manager(oauth_state.user_id, oauth_state.workspace_id)
            provider = self._providers.get(provider_name)
            installation = await provider.exchange_code(
                code=code,
                code_verifier=oauth_state.code_verifier,
            )
            await provider.verify_connection(installation.access_token)
            cipher = self._cipher()
            connection = await self._integrations.upsert_connection(
                workspace_id=oauth_state.workspace_id,
                provider=provider_name,
                connected_by_id=oauth_state.user_id,
                installation=installation,
                access_token_encrypted=cipher.encrypt(installation.access_token),
                refresh_token_encrypted=(
                    cipher.encrypt(installation.refresh_token)
                    if installation.refresh_token is not None
                    else None
                ),
            )
            await self._integrations.ensure_subscriptions(connection.id, self.supported_events)
        except (IntegrationProviderError, IntegrationProviderUnavailableError):
            return self._callback_redirect(oauth_state.return_path, error="provider_failed")
        except (IntegrationAccessDeniedError, WorkspaceNotFoundError):
            return self._callback_redirect(oauth_state.return_path, error="permission_denied")
        except IntegrationConfigurationError:
            return self._callback_redirect(oauth_state.return_path, error="configuration_error")
        return self._callback_redirect(oauth_state.return_path, connected=provider_name.value)

    async def list_destinations(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> list[ProviderDestination]:
        await self._require_manager(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        provider = self._providers.get(connection.provider)
        return await provider.list_destinations(self._access_token(connection))

    async def list_subscriptions(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> list[IntegrationSubscription]:
        await self._require_membership(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        return await self._integrations.ensure_subscriptions(
            connection.id,
            self.supported_events,
        )

    async def update_subscriptions(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
        updates: list[IntegrationSubscriptionUpdate],
    ) -> list[IntegrationSubscription]:
        await self._require_manager(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        unsupported = {item.event_type for item in updates} - set(self.supported_events)
        if unsupported:
            raise IntegrationConfigurationError("Unsupported integration event type")
        return await self._integrations.update_subscriptions(
            connection.id,
            [
                SubscriptionConfiguration(
                    event_type=item.event_type,
                    enabled=item.enabled,
                    destination_id=item.destination_id,
                    destination_name=item.destination_name,
                    configuration=item.configuration,
                )
                for item in updates
            ],
        )

    async def send_test(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
        destination_id: str | None,
    ) -> None:
        await self._require_manager(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        selected_destination = destination_id
        if selected_destination is None:
            subscriptions = await self._integrations.list_subscriptions(connection.id)
            selected_destination = next(
                (
                    subscription.destination_id
                    for subscription in subscriptions
                    if subscription.enabled and subscription.destination_id
                ),
                None,
            )
        if selected_destination is None:
            raise IntegrationConfigurationError("Select a destination before sending a test")
        provider = self._providers.get(connection.provider)
        token = self._access_token(connection)
        await provider.verify_connection(token)
        await provider.send_test_message(token, selected_destination)
        await self._integrations.mark_verified(connection, datetime.now(UTC))

    async def list_deliveries(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[IntegrationDelivery]:
        await self._require_membership(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        return await self._integrations.list_deliveries(
            connection.id,
            limit=limit,
            offset=offset,
        )

    async def disconnect(
        self,
        current_user: User,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> None:
        await self._require_manager(current_user.id, workspace_id)
        connection = await self._require_connection(workspace_id, connection_id)
        provider = self._providers.get(connection.provider)
        await provider.revoke(self._access_token(connection))
        await self._integrations.mark_revoked(connection)

    async def _require_membership(self, user_id: UUID, workspace_id: UUID) -> None:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError

    async def _require_manager(self, user_id: UUID, workspace_id: UUID) -> None:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        if not can_manage_workspace(membership.role):
            raise IntegrationAccessDeniedError

    async def _require_connection(
        self,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> IntegrationConnection:
        connection = await self._integrations.get_connection(workspace_id, connection_id)
        if connection is None:
            raise IntegrationNotFoundError
        return connection

    def _access_token(self, connection: IntegrationConnection) -> str:
        if connection.status is not IntegrationConnectionStatus.ACTIVE:
            raise IntegrationConfigurationError("Integration connection is not active")
        if connection.token_expires_at is not None and connection.token_expires_at <= datetime.now(
            UTC
        ):
            raise IntegrationConfigurationError("Integration credentials have expired")
        if connection.access_token_encrypted is None:
            raise IntegrationConfigurationError("Integration credentials are unavailable")
        return self._cipher().decrypt(connection.access_token_encrypted)

    def _cipher(self) -> IntegrationTokenCipher:
        return IntegrationTokenCipher(self._settings.integration_token_encryption_key)

    def _callback_redirect(
        self,
        return_path: str,
        **query: str,
    ) -> str:
        return f"{self._settings.frontend_url.rstrip('/')}{return_path}?{urlencode(query)}"
