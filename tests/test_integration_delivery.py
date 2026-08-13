from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from cryptography.fernet import Fernet

from app.core.config import Settings
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.integrations.providers.base import IntegrationProviderClient
from app.integrations.token_encryption import IntegrationTokenCipher
from app.models.integration import (
    IntegrationConnection,
    IntegrationConnectionStatus,
    IntegrationDelivery,
    IntegrationDeliveryStatus,
    IntegrationEventType,
    IntegrationOutboxEvent,
    IntegrationProvider,
)
from app.repositories.integration import IntegrationRepository
from app.services.integration_delivery import (
    IntegrationDeliveryService,
    IntegrationTaskPublisher,
)


def make_service() -> tuple[
    IntegrationDeliveryService,
    AsyncMock,
    Mock,
    Mock,
    Settings,
]:
    repository = AsyncMock(spec=IntegrationRepository)
    registry = Mock(spec=IntegrationProviderRegistry)
    publisher = Mock(spec=IntegrationTaskPublisher)
    settings = Settings(
        _env_file=None,
        frontend_url="https://forkroom.vercel.app",
        integration_token_encryption_key=Fernet.generate_key().decode("ascii"),
        integration_max_retries=3,
    )
    return (
        IntegrationDeliveryService(repository, registry, publisher, settings),
        repository,
        registry,
        publisher,
        settings,
    )


async def test_dispatch_outbox_creates_and_enqueues_deliveries() -> None:
    service, repository, _, publisher, _ = make_service()
    event = IntegrationOutboxEvent(
        id=uuid4(),
        workspace_id=uuid4(),
        event_type=IntegrationEventType.VOTING_OPENED,
        event_id=uuid4(),
        payload={"decision_title": "Choose an API framework"},
        available_at=datetime.now(UTC),
    )
    deliveries = [
        IntegrationDelivery(
            id=uuid4(),
            connection_id=uuid4(),
            event_type=event.event_type,
            event_id=event.event_id,
            request_summary={},
        ),
        IntegrationDelivery(
            id=uuid4(),
            connection_id=uuid4(),
            event_type=event.event_type,
            event_id=event.event_id,
            request_summary={},
        ),
    ]
    repository.claim_outbox_event.return_value = event
    repository.create_deliveries.return_value = deliveries

    count = await service.dispatch_outbox(event.id)

    assert count == 2
    assert publisher.enqueue_delivery.call_count == 2
    publisher.enqueue_delivery.assert_any_call(deliveries[0].id)
    publisher.enqueue_delivery.assert_any_call(deliveries[1].id)


async def test_delivery_decrypts_token_and_posts_safe_slack_message() -> None:
    service, repository, registry, _, settings = make_service()
    workspace_id = uuid4()
    decision_id = uuid4()
    connection_id = uuid4()
    delivery = IntegrationDelivery(
        id=uuid4(),
        connection_id=connection_id,
        event_type=IntegrationEventType.DECISION_LOCKED,
        event_id=uuid4(),
        status=IntegrationDeliveryStatus.PENDING,
        attempt_count=1,
        request_summary={
            "destination_id": "C123",
            "payload": {
                "workspace_id": str(workspace_id),
                "decision_id": str(decision_id),
                "decision_title": "Choose an API framework",
                "actor_name": "Raman Singh",
            },
        },
    )
    connection = IntegrationConnection(
        id=connection_id,
        workspace_id=workspace_id,
        provider=IntegrationProvider.SLACK,
        status=IntegrationConnectionStatus.ACTIVE,
        external_account_id="T123",
        external_account_name="ForkRoom",
        connected_by_id=uuid4(),
        access_token_encrypted=IntegrationTokenCipher(
            settings.integration_token_encryption_key
        ).encrypt("xoxb-secret"),
    )
    provider = Mock(spec=IntegrationProviderClient)
    provider.send_message = AsyncMock()
    repository.claim_delivery.return_value = delivery
    repository.get_connection_by_id.return_value = connection
    registry.get.return_value = provider

    result = await service.deliver(delivery.id)

    assert result == "delivered"
    provider.send_message.assert_awaited_once()
    token, destination, message = provider.send_message.await_args.args
    assert token == "xoxb-secret"
    assert destination == "C123"
    assert "Decision locked" in message.text
    assert "xoxb-secret" not in repr(message)
    assert message.blocks[-1]["elements"][0]["url"] == (
        f"https://forkroom.vercel.app/w/{workspace_id}/decisions/{decision_id}"
    )
    repository.mark_delivery_delivered.assert_awaited_once()


async def test_delivery_is_marked_failed_after_attempt_limit() -> None:
    service, repository, _, _, _ = make_service()
    delivery = IntegrationDelivery(
        id=uuid4(),
        connection_id=uuid4(),
        event_type=IntegrationEventType.VOTING_CLOSED,
        event_id=uuid4(),
        status=IntegrationDeliveryStatus.DELIVERING,
        attempt_count=3,
        request_summary={},
    )
    repository.get_delivery.return_value = delivery

    attempts = await service.record_delivery_error(delivery.id, RuntimeError("secret"))

    assert attempts == 3
    repository.mark_delivery_failed.assert_awaited_once_with(delivery.id, "RuntimeError")
    repository.schedule_delivery_retry.assert_not_awaited()
