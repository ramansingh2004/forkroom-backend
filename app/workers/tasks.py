import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import Task
from celery.exceptions import Reject
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AttachmentValidationError
from app.dependencies.integration_events import CeleryIntegrationTaskPublisher
from app.integrations.email import EmailService
from app.integrations.object_storage import ObjectStorage
from app.integrations.pdf_export import DecisionPdfRenderer
from app.integrations.provider_registry import IntegrationProviderRegistry
from app.models.attachment import AttachmentStatus
from app.models.export_search import ExportStatus
from app.models.notification import Notification
from app.repositories.attachment import AttachmentRepository
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.export_search import DecisionExportRepository, SearchRepository
from app.repositories.integration import IntegrationRepository
from app.repositories.notification import NotificationRepository
from app.services.attachment import AttachmentProcessingService
from app.services.export_search import DecisionExportProcessingService, SearchIndexService
from app.services.integration_delivery import IntegrationDeliveryService
from app.services.notification import NotificationPublisher, ReminderDiscoveryService
from app.workers.celery_app import celery_app
from app.workers.database import WorkerSessionFactory

settings = get_settings()


class CeleryNotificationPublisher(NotificationPublisher):
    def enqueue_delivery(self, notification_id: UUID) -> None:
        deliver_notification.apply_async(args=[str(notification_id)])


async def _discover_reminders() -> int:
    async with WorkerSessionFactory() as session:
        service = ReminderDiscoveryService(
            NotificationRepository(session),
            CeleryNotificationPublisher(),
            reminder_window_minutes=settings.reminder_window_minutes,
            max_delivery_attempts=settings.notification_max_delivery_attempts,
        )
        return await service.discover()


async def _recover_stale_deliveries() -> int:
    async with WorkerSessionFactory() as session:
        service = ReminderDiscoveryService(
            NotificationRepository(session),
            CeleryNotificationPublisher(),
            reminder_window_minutes=settings.reminder_window_minutes,
            max_delivery_attempts=settings.notification_max_delivery_attempts,
        )
        return await service.recover_stale()


async def _claim(notification_id: UUID) -> tuple[Notification, str, str] | None:
    async with WorkerSessionFactory() as session:
        repository = NotificationRepository(session)
        notification = await repository.claim_for_delivery(notification_id, datetime.now(UTC))
        if notification is None:
            return None
        recipient = await repository.get_recipient(notification.recipient_id)
        if recipient is None or not recipient.is_active:
            await repository.mark_failed(
                notification,
                now=datetime.now(UTC),
                error="Notification recipient is unavailable",
            )
            return None
        return notification, recipient.email, recipient.display_name


async def _send_and_mark_delivered(
    notification: Notification,
    recipient: str,
    display_name: str,
) -> None:
    await EmailService(settings).send_notification_email(
        recipient,
        display_name,
        subject=notification.title,
        body=notification.body,
    )
    async with WorkerSessionFactory() as session:
        repository = NotificationRepository(session)
        current = await repository.get_for_recipient(notification.id, notification.recipient_id)
        if current is not None:
            await repository.mark_delivered(current, datetime.now(UTC))


async def _record_retry(
    notification: Notification,
    error: Exception,
    countdown: int,
) -> bool:
    async with WorkerSessionFactory() as session:
        repository = NotificationRepository(session)
        current = await repository.get_for_recipient(notification.id, notification.recipient_id)
        if current is None:
            return False
        if current.attempt_count >= current.max_attempts:
            await repository.mark_failed(
                current,
                now=datetime.now(UTC),
                error=str(error),
            )
            return False
        await repository.schedule_retry(
            current,
            available_at=datetime.now(UTC) + timedelta(seconds=countdown),
            error=str(error),
        )
        return True


@celery_app.task(name="forkroom.reminders.discover")  # type: ignore[untyped-decorator]
def discover_reminders() -> int:
    return asyncio.run(_discover_reminders())


@celery_app.task(name="forkroom.notifications.recover")  # type: ignore[untyped-decorator]
def recover_stale_notification_deliveries() -> int:
    return asyncio.run(_recover_stale_deliveries())


async def _process_attachment(attachment_id: UUID) -> str:
    async with WorkerSessionFactory() as session:
        service = AttachmentProcessingService(
            AttachmentRepository(session),
            ObjectStorage(settings),
            max_bytes=settings.attachment_max_bytes,
        )
        return await service.process(attachment_id)


async def _reject_attachment(attachment_id: UUID, error: Exception) -> None:
    async with WorkerSessionFactory() as session:
        repository = AttachmentRepository(session)
        attachment = await repository.get_by_id(attachment_id)
        if attachment is not None and attachment.status is AttachmentStatus.PROCESSING:
            await repository.mark_rejected(
                attachment,
                error=str(error),
                processed_at=datetime.now(UTC),
            )


async def _attachment_attempt_limit_reached(attachment_id: UUID) -> bool:
    async with WorkerSessionFactory() as session:
        attachment = await AttachmentRepository(session).get_by_id(attachment_id)
        return bool(
            attachment is not None
            and attachment.processing_attempts >= settings.attachment_processing_max_attempts
        )


async def _recover_attachment_processing() -> int:
    async with WorkerSessionFactory() as session:
        attachments = await AttachmentRepository(session).list_processing()
    for attachment in attachments:
        process_attachment.apply_async(args=[str(attachment.id)])
    return len(attachments)


@celery_app.task(name="forkroom.attachments.recover")  # type: ignore[untyped-decorator]
def recover_attachment_processing() -> int:
    return asyncio.run(_recover_attachment_processing())


async def _process_export(export_id: UUID) -> str:
    async with WorkerSessionFactory() as session:
        service = DecisionExportProcessingService(
            DecisionExportRepository(session),
            DecisionLockRepository(session),
            ObjectStorage(settings),
            DecisionPdfRenderer(),
        )
        return await service.process(export_id)


async def _fail_export(export_id: UUID, error: Exception) -> int:
    async with WorkerSessionFactory() as session:
        repository = DecisionExportRepository(session)
        export = await repository.get_by_id(export_id)
        if export is None:
            return 0
        if export.status is ExportStatus.PROCESSING:
            await repository.mark_failed(export, str(error))
        return export.attempt_count


async def _recover_exports() -> int:
    async with WorkerSessionFactory() as session:
        exports = await DecisionExportRepository(session).list_incomplete()
    for export in exports:
        generate_decision_export.apply_async(args=[str(export.id)])
    return len(exports)


@celery_app.task(name="forkroom.exports.recover")  # type: ignore[untyped-decorator]
def recover_decision_exports() -> int:
    return asyncio.run(_recover_exports())


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.exports.generate",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def generate_decision_export(self: Task, export_id: str) -> str:
    parsed_id = UUID(export_id)
    try:
        return asyncio.run(_process_export(parsed_id))
    except Exception as error:
        attempts = asyncio.run(_fail_export(parsed_id, error))
        if attempts >= settings.export_processing_max_attempts:
            raise Reject(str(error), requeue=False) from error
        retries = int(self.request.retries)
        countdown = min(
            settings.notification_retry_base_seconds * (2**retries),
            settings.notification_retry_max_seconds,
        )
        raise self.retry(
            exc=error,
            countdown=countdown,
            max_retries=settings.export_processing_max_attempts - 1,
        ) from error


async def _refresh_search() -> int:
    async with WorkerSessionFactory() as session:
        decision_ids = await SearchIndexService(SearchRepository(session)).stale()
    for decision_id in decision_ids:
        index_decision.apply_async(args=[str(decision_id)])
    return len(decision_ids)


async def _index_decision(decision_id: UUID) -> str:
    async with WorkerSessionFactory() as session:
        return await SearchIndexService(SearchRepository(session)).index(decision_id)


@celery_app.task(name="forkroom.search.refresh")  # type: ignore[untyped-decorator]
def refresh_search_index() -> int:
    return asyncio.run(_refresh_search())


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.search.index",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def index_decision(self: Task, decision_id: str) -> str:
    try:
        return asyncio.run(_index_decision(UUID(decision_id)))
    except Exception as error:
        retries = int(self.request.retries)
        countdown = min(
            settings.notification_retry_base_seconds * (2**retries),
            settings.notification_retry_max_seconds,
        )
        raise self.retry(exc=error, countdown=countdown, max_retries=4) from error


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.attachments.process",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def process_attachment(self: Task, attachment_id: str) -> str:
    parsed_id = UUID(attachment_id)
    try:
        return asyncio.run(_process_attachment(parsed_id))
    except AttachmentValidationError as error:
        asyncio.run(_reject_attachment(parsed_id, error))
        raise Reject(str(error), requeue=False) from error
    except Exception as error:
        retries = int(self.request.retries)
        if asyncio.run(_attachment_attempt_limit_reached(parsed_id)):
            asyncio.run(_reject_attachment(parsed_id, error))
            raise Reject(str(error), requeue=False) from error
        countdown = min(
            settings.notification_retry_base_seconds * (2**retries),
            settings.notification_retry_max_seconds,
        )
        raise self.retry(
            exc=error,
            countdown=countdown,
            max_retries=settings.attachment_processing_max_attempts - 1,
        ) from error


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.notifications.deliver",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def deliver_notification(self: Task, notification_id: str) -> str:
    claimed = asyncio.run(_claim(UUID(notification_id)))
    if claimed is None:
        return "ignored"
    notification, recipient, display_name = claimed
    try:
        asyncio.run(_send_and_mark_delivered(notification, recipient, display_name))
    except Exception as error:
        retries = int(self.request.retries)
        countdown = min(
            settings.notification_retry_base_seconds * (2**retries),
            settings.notification_retry_max_seconds,
        )
        should_retry = asyncio.run(_record_retry(notification, error, countdown))
        if should_retry:
            raise self.retry(
                exc=error,
                countdown=countdown,
                max_retries=settings.notification_max_delivery_attempts - 1,
            ) from error
        raise Reject(str(error), requeue=False) from error
    return "delivered"


def _integration_service(session: AsyncSession) -> IntegrationDeliveryService:
    return IntegrationDeliveryService(
        IntegrationRepository(session),
        IntegrationProviderRegistry(settings),
        CeleryIntegrationTaskPublisher(),
        settings,
    )


async def _dispatch_integration_event(event_id: UUID) -> int:
    async with WorkerSessionFactory() as session:
        return await _integration_service(session).dispatch_outbox(event_id)


async def _record_integration_outbox_error(event_id: UUID, error: Exception) -> int:
    async with WorkerSessionFactory() as session:
        return await _integration_service(session).record_outbox_error(event_id, error)


async def _deliver_integration_event(delivery_id: UUID) -> str:
    async with WorkerSessionFactory() as session:
        return await _integration_service(session).deliver(delivery_id)


async def _record_integration_delivery_error(
    delivery_id: UUID,
    error: Exception,
) -> int:
    async with WorkerSessionFactory() as session:
        return await _integration_service(session).record_delivery_error(delivery_id, error)


async def _recover_integration_events() -> int:
    async with WorkerSessionFactory() as session:
        outbox_count, delivery_count = await _integration_service(session).recover()
        return outbox_count + delivery_count


@celery_app.task(name="forkroom.integrations.recover")  # type: ignore[untyped-decorator]
def recover_integration_events() -> int:
    return asyncio.run(_recover_integration_events())


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.integrations.dispatch",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def dispatch_integration_event(self: Task, event_id: str) -> int:
    parsed_id = UUID(event_id)
    try:
        return asyncio.run(_dispatch_integration_event(parsed_id))
    except Exception as error:
        attempts = asyncio.run(_record_integration_outbox_error(parsed_id, error))
        if attempts >= settings.integration_max_retries:
            raise Reject(str(error), requeue=False) from error
        countdown = min(
            settings.notification_retry_base_seconds * (2 ** max(attempts - 1, 0)),
            settings.notification_retry_max_seconds,
        )
        raise self.retry(
            exc=error,
            countdown=countdown,
            max_retries=settings.integration_max_retries - 1,
        ) from error


@celery_app.task(
    bind=True,
    base=Task,
    name="forkroom.integrations.deliver",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def deliver_integration_event(self: Task, delivery_id: str) -> str:
    parsed_id = UUID(delivery_id)
    try:
        return asyncio.run(_deliver_integration_event(parsed_id))
    except Exception as error:
        attempts = asyncio.run(_record_integration_delivery_error(parsed_id, error))
        if attempts >= settings.integration_max_retries:
            raise Reject(str(error), requeue=False) from error
        countdown = min(
            settings.notification_retry_base_seconds * (2 ** max(attempts - 1, 0)),
            settings.notification_retry_max_seconds,
        )
        raise self.retry(
            exc=error,
            countdown=countdown,
            max_retries=settings.integration_max_retries - 1,
        ) from error
