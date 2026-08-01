import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import Task
from celery.exceptions import Reject

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.integrations.email import EmailService
from app.models.notification import Notification
from app.repositories.notification import NotificationRepository
from app.services.notification import NotificationPublisher, ReminderDiscoveryService
from app.workers.celery_app import celery_app

settings = get_settings()


class CeleryNotificationPublisher(NotificationPublisher):
    def enqueue_delivery(self, notification_id: UUID) -> None:
        deliver_notification.apply_async(args=[str(notification_id)])


async def _discover_reminders() -> int:
    async with async_session_factory() as session:
        service = ReminderDiscoveryService(
            NotificationRepository(session),
            CeleryNotificationPublisher(),
            reminder_window_minutes=settings.reminder_window_minutes,
            max_delivery_attempts=settings.notification_max_delivery_attempts,
        )
        return await service.discover()


async def _recover_stale_deliveries() -> int:
    async with async_session_factory() as session:
        service = ReminderDiscoveryService(
            NotificationRepository(session),
            CeleryNotificationPublisher(),
            reminder_window_minutes=settings.reminder_window_minutes,
            max_delivery_attempts=settings.notification_max_delivery_attempts,
        )
        return await service.recover_stale()


async def _claim(notification_id: UUID) -> tuple[Notification, str, str] | None:
    async with async_session_factory() as session:
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
    async with async_session_factory() as session:
        repository = NotificationRepository(session)
        current = await repository.get_for_recipient(notification.id, notification.recipient_id)
        if current is not None:
            await repository.mark_delivered(current, datetime.now(UTC))


async def _record_retry(
    notification: Notification,
    error: Exception,
    countdown: int,
) -> bool:
    async with async_session_factory() as session:
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
