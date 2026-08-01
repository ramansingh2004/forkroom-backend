from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.exceptions import NotificationNotFoundError
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification import NotificationRepository, ReminderCandidate


class NotificationPublisher(Protocol):
    def enqueue_delivery(self, notification_id: UUID) -> None: ...


class NotificationService:
    def __init__(self, repository: NotificationRepository) -> None:
        self._notifications = repository

    async def list_notifications(
        self,
        current_user: User,
        *,
        unread_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int, int]:
        return await self._notifications.list_for_recipient(
            current_user.id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )

    async def get_notification(
        self,
        current_user: User,
        notification_id: UUID,
    ) -> Notification:
        notification = await self._notifications.get_for_recipient(
            notification_id,
            current_user.id,
        )
        if notification is None:
            raise NotificationNotFoundError
        return notification

    async def mark_read(
        self,
        current_user: User,
        notification_id: UUID,
    ) -> Notification:
        notification = await self.get_notification(current_user, notification_id)
        return await self._notifications.mark_read(notification, datetime.now(UTC))

    async def mark_all_read(self, current_user: User) -> int:
        return await self._notifications.mark_all_read(current_user.id, datetime.now(UTC))

    async def unread_count(self, current_user: User) -> int:
        return await self._notifications.unread_count(current_user.id)


class ReminderDiscoveryService:
    def __init__(
        self,
        repository: NotificationRepository,
        publisher: NotificationPublisher,
        *,
        reminder_window_minutes: int,
        max_delivery_attempts: int,
    ) -> None:
        self._notifications = repository
        self._publisher = publisher
        self._window = timedelta(minutes=reminder_window_minutes)
        self._max_delivery_attempts = max_delivery_attempts

    async def discover(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        before = current + self._window
        loaders: tuple[
            Callable[..., Awaitable[list[ReminderCandidate]]],
            ...,
        ] = (
            self._notifications.due_action_candidates,
            self._notifications.due_review_candidates,
            self._notifications.due_decision_candidates,
            self._notifications.due_voting_candidates,
        )
        created = 0
        for load in loaders:
            for candidate in await load(after=current, before=before):
                notification_id = await self._notifications.create_candidate(
                    candidate,
                    max_attempts=self._max_delivery_attempts,
                    available_at=current,
                )
                if notification_id is not None:
                    self._publisher.enqueue_delivery(notification_id)
                    created += 1
        return created

    async def recover_stale(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        recovered_ids = await self._notifications.recover_stale_deliveries(
            stale_before=current - timedelta(minutes=10),
            available_at=current,
        )
        for notification_id in recovered_ids:
            self._publisher.enqueue_delivery(notification_id)
        return len(recovered_ids)
