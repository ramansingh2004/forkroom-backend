from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.controllers.notification import get_notification
from app.core.exceptions import NotificationNotFoundError
from app.dependencies.auth import get_current_user
from app.dependencies.notification import get_notification_service
from app.main import app
from app.models.notification import Notification, NotificationKind, NotificationStatus
from app.models.user import User
from app.repositories.notification import ReminderCandidate
from app.services.notification import (
    NotificationService,
    ReminderDiscoveryService,
)


def make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman",
        is_active=True,
        is_email_verified=True,
        auth_version=0,
        created_at=now,
        updated_at=now,
    )


def make_notification(user: User) -> Notification:
    now = datetime.now(UTC)
    return Notification(
        id=uuid4(),
        recipient_id=user.id,
        workspace_id=uuid4(),
        kind=NotificationKind.ACTION_DUE,
        source_id=uuid4(),
        idempotency_key=f"action:{uuid4()}",
        title="Action due",
        body="Complete the implementation.",
        status=NotificationStatus.PENDING,
        attempt_count=0,
        max_attempts=5,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


def make_candidate(kind: NotificationKind = NotificationKind.ACTION_DUE) -> ReminderCandidate:
    return ReminderCandidate(
        recipient_id=uuid4(),
        workspace_id=uuid4(),
        kind=kind,
        source_id=uuid4(),
        due_at=datetime.now(UTC) + timedelta(minutes=30),
        title="Reminder",
        body="Something is due soon.",
    )


@pytest.mark.asyncio
async def test_notification_service_gets_owned_notification() -> None:
    user = make_user()
    notification = make_notification(user)
    repository = Mock()
    repository.get_for_recipient = AsyncMock(return_value=notification)
    service = NotificationService(repository)

    result = await service.get_notification(user, notification.id)

    assert result is notification
    repository.get_for_recipient.assert_awaited_once_with(notification.id, user.id)


@pytest.mark.asyncio
async def test_notification_service_hides_unknown_notification() -> None:
    repository = Mock()
    repository.get_for_recipient = AsyncMock(return_value=None)
    service = NotificationService(repository)

    with pytest.raises(NotificationNotFoundError):
        await service.get_notification(make_user(), uuid4())


@pytest.mark.asyncio
async def test_notification_service_marks_one_read() -> None:
    user = make_user()
    notification = make_notification(user)
    repository = Mock()
    repository.get_for_recipient = AsyncMock(return_value=notification)
    repository.mark_read = AsyncMock(return_value=notification)
    service = NotificationService(repository)

    result = await service.mark_read(user, notification.id)

    assert result is notification
    repository.mark_read.assert_awaited_once()


@pytest.mark.asyncio
async def test_notification_service_marks_all_read() -> None:
    user = make_user()
    repository = Mock()
    repository.mark_all_read = AsyncMock(return_value=3)
    service = NotificationService(repository)

    assert await service.mark_all_read(user) == 3


@pytest.mark.asyncio
async def test_notification_service_lists_with_pagination() -> None:
    user = make_user()
    notification = make_notification(user)
    repository = Mock()
    repository.list_for_recipient = AsyncMock(return_value=([notification], 1, 1))
    service = NotificationService(repository)

    result = await service.list_notifications(
        user,
        unread_only=True,
        limit=20,
        offset=5,
    )

    assert result == ([notification], 1, 1)
    repository.list_for_recipient.assert_awaited_once_with(
        user.id,
        unread_only=True,
        limit=20,
        offset=5,
    )


@pytest.mark.asyncio
async def test_notification_service_returns_unread_count() -> None:
    repository = Mock()
    repository.unread_count = AsyncMock(return_value=7)
    service = NotificationService(repository)

    assert await service.unread_count(make_user()) == 7


@pytest.mark.asyncio
async def test_discovery_creates_and_publishes_notification() -> None:
    candidate = make_candidate()
    notification_id = uuid4()
    repository = Mock()
    repository.due_action_candidates = AsyncMock(return_value=[candidate])
    repository.due_review_candidates = AsyncMock(return_value=[])
    repository.due_decision_candidates = AsyncMock(return_value=[])
    repository.due_voting_candidates = AsyncMock(return_value=[])
    repository.create_candidate = AsyncMock(return_value=notification_id)
    publisher = Mock()
    service = ReminderDiscoveryService(
        repository,
        publisher,
        reminder_window_minutes=60,
        max_delivery_attempts=5,
    )

    assert await service.discover(datetime.now(UTC)) == 1
    publisher.enqueue_delivery.assert_called_once_with(notification_id)


@pytest.mark.asyncio
async def test_discovery_does_not_publish_duplicate() -> None:
    repository = Mock()
    repository.due_action_candidates = AsyncMock(return_value=[make_candidate()])
    repository.due_review_candidates = AsyncMock(return_value=[])
    repository.due_decision_candidates = AsyncMock(return_value=[])
    repository.due_voting_candidates = AsyncMock(return_value=[])
    repository.create_candidate = AsyncMock(return_value=None)
    publisher = Mock()
    service = ReminderDiscoveryService(
        repository,
        publisher,
        reminder_window_minutes=60,
        max_delivery_attempts=5,
    )

    assert await service.discover(datetime.now(UTC)) == 0
    publisher.enqueue_delivery.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_checks_all_four_sources() -> None:
    candidates = [
        make_candidate(NotificationKind.ACTION_DUE),
        make_candidate(NotificationKind.DECISION_REVIEW),
        make_candidate(NotificationKind.DECISION_DEADLINE),
        make_candidate(NotificationKind.VOTING_CLOSE),
    ]
    repository = Mock()
    repository.due_action_candidates = AsyncMock(return_value=[candidates[0]])
    repository.due_review_candidates = AsyncMock(return_value=[candidates[1]])
    repository.due_decision_candidates = AsyncMock(return_value=[candidates[2]])
    repository.due_voting_candidates = AsyncMock(return_value=[candidates[3]])
    repository.create_candidate = AsyncMock(side_effect=[uuid4() for _ in range(4)])
    service = ReminderDiscoveryService(
        repository,
        Mock(),
        reminder_window_minutes=60,
        max_delivery_attempts=5,
    )

    assert await service.discover(datetime.now(UTC)) == 4
    assert repository.create_candidate.await_count == 4


@pytest.mark.asyncio
async def test_discovery_recovers_stale_delivery_leases() -> None:
    recovered_ids = [uuid4(), uuid4()]
    repository = Mock()
    repository.recover_stale_deliveries = AsyncMock(return_value=recovered_ids)
    publisher = Mock()
    service = ReminderDiscoveryService(
        repository,
        publisher,
        reminder_window_minutes=60,
        max_delivery_attempts=5,
    )

    assert await service.recover_stale(datetime.now(UTC)) == 2
    assert publisher.enqueue_delivery.call_count == 2


def test_reminder_candidate_has_stable_idempotency_key() -> None:
    candidate = make_candidate()

    assert candidate.idempotency_key == (
        f"{candidate.kind.value}:{candidate.source_id}:"
        f"{candidate.recipient_id}:{candidate.due_at.isoformat()}"
    )


@pytest.mark.asyncio
async def test_notification_controller_maps_missing_to_404() -> None:
    service = Mock()
    service.get_notification = AsyncMock(side_effect=NotificationNotFoundError)

    with pytest.raises(Exception) as error:
        await get_notification(uuid4(), make_user(), service)

    assert getattr(error.value, "status_code", None) == 404


@pytest.fixture
def notification_api_overrides() -> tuple[User, Notification, Mock]:
    user = make_user()
    notification = make_notification(user)
    service = Mock()
    service.list_notifications = AsyncMock(return_value=([notification], 1, 1))
    service.unread_count = AsyncMock(return_value=1)
    service.get_notification = AsyncMock(return_value=notification)
    service.mark_read = AsyncMock(return_value=notification)
    service.mark_all_read = AsyncMock(return_value=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_notification_service] = lambda: service
    yield user, notification, service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_notifications_api(
    client: AsyncClient,
    notification_api_overrides: tuple[User, Notification, Mock],
) -> None:
    response = await client.get("/api/v1/notifications?unread_only=true")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Action due"


@pytest.mark.asyncio
async def test_unread_notification_count_api(
    client: AsyncClient,
    notification_api_overrides: tuple[User, Notification, Mock],
) -> None:
    response = await client.get("/api/v1/notifications/unread-count")

    assert response.status_code == 200
    assert response.json() == {"unread": 1}


@pytest.mark.asyncio
async def test_get_notification_api(
    client: AsyncClient,
    notification_api_overrides: tuple[User, Notification, Mock],
) -> None:
    _, notification, _ = notification_api_overrides
    response = await client.get(f"/api/v1/notifications/{notification.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(notification.id)


@pytest.mark.asyncio
async def test_mark_notification_read_api(
    client: AsyncClient,
    notification_api_overrides: tuple[User, Notification, Mock],
) -> None:
    _, notification, service = notification_api_overrides
    response = await client.post(f"/api/v1/notifications/{notification.id}/read")

    assert response.status_code == 200
    service.mark_read.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_all_notifications_read_api(
    client: AsyncClient,
    notification_api_overrides: tuple[User, Notification, Mock],
) -> None:
    response = await client.post("/api/v1/notifications/read-all")

    assert response.status_code == 200
    assert response.json() == {"updated": 1}
