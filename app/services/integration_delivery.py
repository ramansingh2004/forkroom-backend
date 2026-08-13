from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import IntegrationConfigurationError
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.integrations.providers.base import ProviderMessage
from app.integrations.token_encryption import IntegrationTokenCipher
from app.models.integration import (
    IntegrationConnectionStatus,
    IntegrationDelivery,
    IntegrationEventType,
    IntegrationOutboxEvent,
)
from app.repositories.integration import IntegrationRepository


class IntegrationTaskPublisher(Protocol):
    def enqueue_outbox(self, event_id: UUID) -> None: ...

    def enqueue_delivery(self, delivery_id: UUID) -> None: ...


class IntegrationEventEmitter:
    def __init__(
        self,
        repository: IntegrationRepository,
        publisher: IntegrationTaskPublisher,
    ) -> None:
        self._repository = repository
        self._publisher = publisher

    def stage(
        self,
        *,
        workspace_id: UUID,
        event_type: IntegrationEventType,
        event_id: UUID,
        payload: dict[str, object],
        available_at: datetime | None = None,
    ) -> IntegrationOutboxEvent:
        return self._repository.stage_outbox_event(
            workspace_id=workspace_id,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            available_at=available_at or datetime.now(UTC),
        )

    def publish(self, event: IntegrationOutboxEvent) -> None:
        self._publisher.enqueue_outbox(event.id)


class IntegrationDeliveryService:
    def __init__(
        self,
        repository: IntegrationRepository,
        providers: IntegrationProviderRegistry,
        publisher: IntegrationTaskPublisher,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._publisher = publisher
        self._settings = settings

    async def dispatch_outbox(self, event_id: UUID) -> int:
        now = datetime.now(UTC)
        event = await self._repository.claim_outbox_event(
            event_id,
            now,
            max_attempts=self._settings.integration_max_retries,
        )
        if event is None:
            return 0
        deliveries = await self._repository.create_deliveries(event, now)
        for delivery in deliveries:
            self._publisher.enqueue_delivery(delivery.id)
        return len(deliveries)

    async def record_outbox_error(self, event_id: UUID, error: Exception) -> int:
        event = await self._repository.get_outbox_event(event_id)
        if event is None:
            return self._settings.integration_max_retries
        countdown = self.retry_countdown(event.attempt_count)
        await self._repository.mark_outbox_failed(
            event_id,
            available_at=datetime.now(UTC) + timedelta(seconds=countdown),
            error=self._error_code(error),
        )
        return event.attempt_count

    async def deliver(self, delivery_id: UUID) -> str:
        delivery = await self._repository.claim_delivery(delivery_id, datetime.now(UTC))
        if delivery is None:
            return "ignored"
        connection = await self._repository.get_connection_by_id(delivery.connection_id)
        if connection is None or connection.status is not IntegrationConnectionStatus.ACTIVE:
            raise IntegrationConfigurationError("Integration connection is not active")
        if connection.access_token_encrypted is None:
            raise IntegrationConfigurationError("Integration credentials are unavailable")

        destination_id = delivery.request_summary.get("destination_id")
        raw_payload = delivery.request_summary.get("payload")
        if not isinstance(destination_id, str) or not isinstance(raw_payload, dict):
            raise IntegrationConfigurationError("Integration delivery payload is invalid")
        payload = cast(dict[str, object], raw_payload)
        token = IntegrationTokenCipher(self._settings.integration_token_encryption_key).decrypt(
            connection.access_token_encrypted
        )
        message = self._message(delivery, payload)
        provider = self._providers.get(connection.provider)
        await provider.send_message(token, destination_id, message)
        await self._repository.mark_delivery_delivered(delivery.id, datetime.now(UTC))
        return "delivered"

    async def record_delivery_error(self, delivery_id: UUID, error: Exception) -> int:
        delivery = await self._repository.get_delivery(delivery_id)
        if delivery is None:
            return self._settings.integration_max_retries
        error_code = self._error_code(error)
        if delivery.attempt_count >= self._settings.integration_max_retries:
            await self._repository.mark_delivery_failed(delivery.id, error_code)
            return delivery.attempt_count
        countdown = self.retry_countdown(delivery.attempt_count)
        await self._repository.schedule_delivery_retry(
            delivery.id,
            next_retry_at=datetime.now(UTC) + timedelta(seconds=countdown),
            error_code=error_code,
        )
        return delivery.attempt_count

    async def recover(self) -> tuple[int, int]:
        now = datetime.now(UTC)
        await self._repository.recover_stale_claims(
            stale_before=now - timedelta(minutes=5),
            available_at=now,
            max_attempts=self._settings.integration_max_retries,
        )
        outbox_events = await self._repository.list_ready_outbox_events(
            now,
            max_attempts=self._settings.integration_max_retries,
        )
        deliveries = await self._repository.list_ready_deliveries(
            now,
            max_attempts=self._settings.integration_max_retries,
        )
        for event in outbox_events:
            self._publisher.enqueue_outbox(event.id)
        for delivery in deliveries:
            self._publisher.enqueue_delivery(delivery.id)
        return len(outbox_events), len(deliveries)

    def retry_countdown(self, attempt_count: int) -> int:
        return int(
            min(
                self._settings.notification_retry_base_seconds * (2 ** max(attempt_count - 1, 0)),
                self._settings.notification_retry_max_seconds,
            )
        )

    def _message(
        self,
        delivery: IntegrationDelivery,
        payload: dict[str, object],
    ) -> ProviderMessage:
        title = self._payload_text(payload, "decision_title", "Untitled decision")
        workspace_id = self._payload_text(payload, "workspace_id", "")
        decision_id = self._payload_text(payload, "decision_id", "")
        actor = self._payload_text(payload, "actor_name", "A workspace member")
        event_labels = {
            IntegrationEventType.DECISION_ACTIVATED: "Decision activated",
            IntegrationEventType.VOTING_OPENED: "Voting opened",
            IntegrationEventType.VOTING_CLOSED: "Voting closed",
            IntegrationEventType.DECISION_LOCKED: "Decision locked",
        }
        label = event_labels.get(delivery.event_type, "Decision updated")
        details = {
            IntegrationEventType.DECISION_ACTIVATED: f"{actor} activated this decision.",
            IntegrationEventType.VOTING_OPENED: f"{actor} opened a voting round.",
            IntegrationEventType.VOTING_CLOSED: f"{actor} closed the voting round.",
            IntegrationEventType.DECISION_LOCKED: f"{actor} locked the final decision record.",
        }.get(delivery.event_type, f"{actor} updated this decision.")
        link = ""
        if workspace_id and decision_id:
            link = (
                f"{self._settings.frontend_url.rstrip('/')}"
                f"/w/{workspace_id}/decisions/{decision_id}"
            )
        text = f"{label}: {title}. {details}"
        blocks: list[dict[str, object]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": label},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{details}",
                },
            },
        ]
        if link:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in ForkRoom"},
                            "url": link,
                        }
                    ],
                }
            )
        return ProviderMessage(
            text=text,
            blocks=blocks,
            idempotency_key=str(delivery.id),
        )

    @staticmethod
    def _payload_text(payload: dict[str, object], key: str, default: str) -> str:
        value = payload.get(key)
        return value if isinstance(value, str) and value else default

    @staticmethod
    def _error_code(error: Exception) -> str:
        name = type(error).__name__
        return name[:100]
