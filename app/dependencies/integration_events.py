import logging
from uuid import UUID

from app.repositories.integration import IntegrationRepository
from app.services.integration_delivery import (
    IntegrationEventEmitter,
    IntegrationTaskPublisher,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class CeleryIntegrationTaskPublisher(IntegrationTaskPublisher):
    def enqueue_outbox(self, event_id: UUID) -> None:
        self._send("forkroom.integrations.dispatch", event_id)

    def enqueue_delivery(self, delivery_id: UUID) -> None:
        self._send("forkroom.integrations.deliver", delivery_id)

    @staticmethod
    def _send(task_name: str, item_id: UUID) -> None:
        try:
            celery_app.send_task(task_name, args=[str(item_id)])
        except Exception:
            # The database remains the source of truth. Celery Beat will recover
            # pending outbox events and deliveries when the broker is available.
            logger.exception("Could not enqueue integration task %s", task_name)


def build_integration_event_emitter(
    repository: IntegrationRepository,
) -> IntegrationEventEmitter:
    return IntegrationEventEmitter(repository, CeleryIntegrationTaskPublisher())
