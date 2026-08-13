from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.providers.base import ProviderInstallation
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationEventType,
    IntegrationProvider,
    IntegrationSubscription,
)


@dataclass(frozen=True, slots=True)
class SubscriptionConfiguration:
    event_type: IntegrationEventType
    enabled: bool
    destination_id: str | None
    destination_name: str | None
    configuration: dict[str, object]


class IntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_connections(self, workspace_id: UUID) -> list[IntegrationConnection]:
        statement = (
            select(IntegrationConnection)
            .where(IntegrationConnection.workspace_id == workspace_id)
            .order_by(IntegrationConnection.created_at.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_connection(
        self,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> IntegrationConnection | None:
        statement = select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.workspace_id == workspace_id,
        )
        return cast(IntegrationConnection | None, await self._session.scalar(statement))

    async def upsert_connection(
        self,
        *,
        workspace_id: UUID,
        provider: IntegrationProvider,
        connected_by_id: UUID,
        installation: ProviderInstallation,
        access_token_encrypted: str,
        refresh_token_encrypted: str | None,
    ) -> IntegrationConnection:
        statement = select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.provider == provider,
            IntegrationConnection.external_account_id == installation.external_account_id,
        )
        connection = cast(
            IntegrationConnection | None,
            await self._session.scalar(statement),
        )
        if connection is None:
            connection = IntegrationConnection(
                workspace_id=workspace_id,
                provider=provider,
                external_account_id=installation.external_account_id,
                external_account_name=installation.external_account_name,
                connected_by_id=connected_by_id,
            )
            self._session.add(connection)
        connection.status = IntegrationConnectionStatus.ACTIVE
        connection.external_account_name = installation.external_account_name
        connection.access_token_encrypted = access_token_encrypted
        connection.refresh_token_encrypted = refresh_token_encrypted
        connection.token_expires_at = installation.expires_at
        connection.scopes = installation.scopes
        connection.configuration = installation.configuration
        connection.connected_by_id = connected_by_id
        connection.last_error = None
        await self._session.commit()
        await self._session.refresh(connection)
        return connection

    async def ensure_subscriptions(
        self,
        connection_id: UUID,
        event_types: tuple[IntegrationEventType, ...],
    ) -> list[IntegrationSubscription]:
        existing = await self.list_subscriptions(connection_id)
        existing_types = {item.event_type for item in existing}
        for current_event_type in event_types:
            if current_event_type not in existing_types:
                self._session.add(
                    IntegrationSubscription(
                        connection_id=connection_id,
                        event_type=current_event_type,
                        enabled=False,
                    )
                )
        await self._session.commit()
        return await self.list_subscriptions(connection_id)

    async def list_subscriptions(self, connection_id: UUID) -> list[IntegrationSubscription]:
        statement = (
            select(IntegrationSubscription)
            .where(IntegrationSubscription.connection_id == connection_id)
            .order_by(IntegrationSubscription.event_type.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def update_subscriptions(
        self,
        connection_id: UUID,
        values: list[SubscriptionConfiguration],
    ) -> list[IntegrationSubscription]:
        existing = {item.event_type: item for item in await self.list_subscriptions(connection_id)}
        for value in values:
            subscription = existing.get(value.event_type)
            if subscription is None:
                subscription = IntegrationSubscription(
                    connection_id=connection_id,
                    event_type=value.event_type,
                )
                self._session.add(subscription)
            subscription.enabled = value.enabled
            subscription.destination_id = value.destination_id
            subscription.destination_name = value.destination_name
            subscription.configuration = value.configuration
        await self._session.commit()
        return await self.list_subscriptions(connection_id)

    async def mark_verified(
        self,
        connection: IntegrationConnection,
        verified_at: datetime,
    ) -> IntegrationConnection:
        connection.status = IntegrationConnectionStatus.ACTIVE
        connection.last_synced_at = verified_at
        connection.last_error = None
        await self._session.commit()
        await self._session.refresh(connection)
        return connection

    async def mark_revoked(self, connection: IntegrationConnection) -> None:
        connection.status = IntegrationConnectionStatus.REVOKED
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        connection.token_expires_at = None
        await self._session.commit()
