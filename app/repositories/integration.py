from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.providers.base import ProviderInstallation
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationDelivery,
    IntegrationDeliveryStatus,
    IntegrationEventType,
    IntegrationOutboxEvent,
    IntegrationOutboxStatus,
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

    def stage_outbox_event(
        self,
        *,
        workspace_id: UUID,
        event_type: IntegrationEventType,
        event_id: UUID,
        payload: dict[str, object],
        available_at: datetime,
    ) -> IntegrationOutboxEvent:
        event = IntegrationOutboxEvent(
            workspace_id=workspace_id,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            available_at=available_at,
        )
        self._session.add(event)
        return event

    async def claim_outbox_event(
        self,
        event_id: UUID,
        now: datetime,
        *,
        max_attempts: int,
    ) -> IntegrationOutboxEvent | None:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.id == event_id,
                IntegrationOutboxEvent.status.in_(
                    {IntegrationOutboxStatus.PENDING, IntegrationOutboxStatus.FAILED}
                ),
                IntegrationOutboxEvent.available_at <= now,
                IntegrationOutboxEvent.attempt_count < max_attempts,
            )
            .with_for_update(skip_locked=True)
        )
        event = cast(
            IntegrationOutboxEvent | None,
            await self._session.scalar(statement),
        )
        if event is None:
            return None
        event.status = IntegrationOutboxStatus.PROCESSING
        event.attempt_count += 1
        event.last_error = None
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def get_outbox_event(
        self,
        event_id: UUID,
    ) -> IntegrationOutboxEvent | None:
        return cast(
            IntegrationOutboxEvent | None,
            await self._session.get(IntegrationOutboxEvent, event_id),
        )

    async def create_deliveries(
        self,
        event: IntegrationOutboxEvent,
        now: datetime,
    ) -> list[IntegrationDelivery]:
        statement = (
            select(IntegrationConnection, IntegrationSubscription)
            .join(
                IntegrationSubscription,
                IntegrationSubscription.connection_id == IntegrationConnection.id,
            )
            .where(
                IntegrationConnection.workspace_id == event.workspace_id,
                IntegrationConnection.status == IntegrationConnectionStatus.ACTIVE,
                IntegrationSubscription.event_type == event.event_type,
                IntegrationSubscription.enabled.is_(True),
                IntegrationSubscription.destination_id.is_not(None),
            )
        )
        rows = (await self._session.execute(statement)).all()
        existing_statement = select(IntegrationDelivery.connection_id).where(
            IntegrationDelivery.event_type == event.event_type,
            IntegrationDelivery.event_id == event.event_id,
        )
        existing_connection_ids = set((await self._session.scalars(existing_statement)).all())
        deliveries: list[IntegrationDelivery] = []
        for connection, subscription in rows:
            if connection.id in existing_connection_ids or subscription.destination_id is None:
                continue
            delivery = IntegrationDelivery(
                connection_id=connection.id,
                event_type=event.event_type,
                event_id=event.event_id,
                request_summary={
                    "workspace_id": str(event.workspace_id),
                    "destination_id": subscription.destination_id,
                    "destination_name": subscription.destination_name,
                    "payload": event.payload,
                },
                next_retry_at=now,
            )
            self._session.add(delivery)
            deliveries.append(delivery)
        event.status = IntegrationOutboxStatus.PROCESSED
        event.processed_at = now
        event.last_error = None
        await self._session.commit()
        for delivery in deliveries:
            await self._session.refresh(delivery)
        return deliveries

    async def mark_outbox_failed(
        self,
        event_id: UUID,
        *,
        available_at: datetime,
        error: str,
    ) -> None:
        event = await self._session.get(IntegrationOutboxEvent, event_id)
        if event is None or event.status is IntegrationOutboxStatus.PROCESSED:
            return
        event.status = IntegrationOutboxStatus.FAILED
        event.available_at = available_at
        event.last_error = error[:2000]
        await self._session.commit()

    async def list_ready_outbox_events(
        self,
        now: datetime,
        *,
        max_attempts: int,
        limit: int = 100,
    ) -> list[IntegrationOutboxEvent]:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.status.in_(
                    {IntegrationOutboxStatus.PENDING, IntegrationOutboxStatus.FAILED}
                ),
                IntegrationOutboxEvent.available_at <= now,
                IntegrationOutboxEvent.attempt_count < max_attempts,
            )
            .order_by(IntegrationOutboxEvent.available_at.asc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def claim_delivery(
        self,
        delivery_id: UUID,
        now: datetime,
    ) -> IntegrationDelivery | None:
        statement = (
            select(IntegrationDelivery)
            .where(
                IntegrationDelivery.id == delivery_id,
                IntegrationDelivery.status.in_(
                    {
                        IntegrationDeliveryStatus.PENDING,
                        IntegrationDeliveryStatus.RETRY_SCHEDULED,
                    }
                ),
                or_(
                    IntegrationDelivery.next_retry_at.is_(None),
                    IntegrationDelivery.next_retry_at <= now,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        delivery = cast(
            IntegrationDelivery | None,
            await self._session.scalar(statement),
        )
        if delivery is None:
            return None
        delivery.status = IntegrationDeliveryStatus.DELIVERING
        delivery.attempt_count += 1
        delivery.error_code = None
        delivery.next_retry_at = None
        await self._session.commit()
        await self._session.refresh(delivery)
        return delivery

    async def get_delivery(
        self,
        delivery_id: UUID,
    ) -> IntegrationDelivery | None:
        return cast(
            IntegrationDelivery | None,
            await self._session.get(IntegrationDelivery, delivery_id),
        )

    async def get_connection_by_id(
        self,
        connection_id: UUID,
    ) -> IntegrationConnection | None:
        return cast(
            IntegrationConnection | None,
            await self._session.get(IntegrationConnection, connection_id),
        )

    async def mark_delivery_delivered(
        self,
        delivery_id: UUID,
        now: datetime,
    ) -> None:
        delivery = await self._session.get(IntegrationDelivery, delivery_id)
        if delivery is None:
            return
        delivery.status = IntegrationDeliveryStatus.DELIVERED
        delivery.delivered_at = now
        delivery.next_retry_at = None
        delivery.error_code = None
        await self._session.commit()

    async def schedule_delivery_retry(
        self,
        delivery_id: UUID,
        *,
        next_retry_at: datetime,
        error_code: str,
    ) -> None:
        delivery = await self._session.get(IntegrationDelivery, delivery_id)
        if delivery is None or delivery.status is IntegrationDeliveryStatus.DELIVERED:
            return
        delivery.status = IntegrationDeliveryStatus.RETRY_SCHEDULED
        delivery.next_retry_at = next_retry_at
        delivery.error_code = error_code[:100]
        await self._session.commit()

    async def mark_delivery_failed(
        self,
        delivery_id: UUID,
        error_code: str,
    ) -> None:
        delivery = await self._session.get(IntegrationDelivery, delivery_id)
        if delivery is None or delivery.status is IntegrationDeliveryStatus.DELIVERED:
            return
        delivery.status = IntegrationDeliveryStatus.FAILED
        delivery.next_retry_at = None
        delivery.error_code = error_code[:100]
        await self._session.commit()

    async def list_ready_deliveries(
        self,
        now: datetime,
        *,
        max_attempts: int,
        limit: int = 100,
    ) -> list[IntegrationDelivery]:
        statement = (
            select(IntegrationDelivery)
            .where(
                IntegrationDelivery.status.in_(
                    {
                        IntegrationDeliveryStatus.PENDING,
                        IntegrationDeliveryStatus.RETRY_SCHEDULED,
                    }
                ),
                IntegrationDelivery.attempt_count < max_attempts,
                or_(
                    IntegrationDelivery.next_retry_at.is_(None),
                    IntegrationDelivery.next_retry_at <= now,
                ),
            )
            .order_by(IntegrationDelivery.created_at.asc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def recover_stale_claims(
        self,
        *,
        stale_before: datetime,
        available_at: datetime,
        max_attempts: int,
    ) -> tuple[int, int]:
        outbox_statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.status == IntegrationOutboxStatus.PROCESSING,
            IntegrationOutboxEvent.updated_at <= stale_before,
        )
        delivery_statement = select(IntegrationDelivery).where(
            IntegrationDelivery.status == IntegrationDeliveryStatus.DELIVERING,
            IntegrationDelivery.updated_at <= stale_before,
        )
        outbox_events = list((await self._session.scalars(outbox_statement)).all())
        deliveries = list((await self._session.scalars(delivery_statement)).all())
        for event in outbox_events:
            event.status = IntegrationOutboxStatus.FAILED
            event.available_at = available_at
            event.last_error = "stale_claim_recovered"
        for delivery in deliveries:
            if delivery.attempt_count >= max_attempts:
                delivery.status = IntegrationDeliveryStatus.FAILED
                delivery.next_retry_at = None
            else:
                delivery.status = IntegrationDeliveryStatus.RETRY_SCHEDULED
                delivery.next_retry_at = available_at
            delivery.error_code = "stale_claim_recovered"
        if outbox_events or deliveries:
            await self._session.commit()
        return len(outbox_events), len(deliveries)

    async def list_deliveries(
        self,
        connection_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[IntegrationDelivery]:
        statement = (
            select(IntegrationDelivery)
            .where(IntegrationDelivery.connection_id == connection_id)
            .order_by(IntegrationDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())
