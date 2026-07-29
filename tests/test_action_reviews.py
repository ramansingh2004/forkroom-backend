from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import ActionAssigneeInvalidError, ReviewConflictError
from app.dependencies.action_review import get_action_review_service
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.action_review import (
    ActionStatus,
    DecisionReview,
    ImplementationAction,
    ReviewStatus,
)
from app.models.user import User
from app.services.action_review import ActionReviewService


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="not-returned",
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture
def action_review_service(current_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=ActionReviewService)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_action_review_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_action_review_service, None)


def base_path(workspace_id: UUID, decision_id: UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}"


def make_action(user: User, decision_id: UUID) -> ImplementationAction:
    now = datetime(2026, 7, 29, tzinfo=UTC)
    return ImplementationAction(
        id=uuid4(),
        decision_id=decision_id,
        created_by_id=user.id,
        assignee_id=user.id,
        title="Deploy the selected architecture",
        description="Release the approved implementation.",
        status=ActionStatus.TODO,
        due_at=now + timedelta(days=14),
        created_at=now,
        updated_at=now,
    )


def make_review(user: User, decision_id: UUID) -> DecisionReview:
    now = datetime(2026, 7, 29, tzinfo=UTC)
    return DecisionReview(
        id=uuid4(),
        decision_id=decision_id,
        scheduled_by_id=user.id,
        scheduled_for=now + timedelta(days=90),
        status=ReviewStatus.SCHEDULED,
        notes="Review operational assumptions.",
        created_at=now,
        updated_at=now,
    )


async def test_create_and_list_actions(
    client: AsyncClient,
    current_user: User,
    action_review_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    action = make_action(current_user, decision_id)
    action_review_service.create_action.return_value = action
    action_review_service.list_actions.return_value = [action]
    path = f"{base_path(workspace_id, decision_id)}/actions"

    create_response = await client.post(
        path,
        json={
            "title": action.title,
            "description": action.description,
            "assignee_id": str(action.assignee_id),
            "due_at": action.due_at.isoformat(),
        },
    )
    list_response = await client.get(
        path,
        params={"status": "todo", "assignee_id": str(action.assignee_id)},
    )

    assert create_response.status_code == 201
    assert create_response.json()["assignee_id"] == str(action.assignee_id)
    assert list_response.status_code == 200
    assert list_response.json()[0]["status"] == "todo"


async def test_transition_action(
    client: AsyncClient,
    current_user: User,
    action_review_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    action = make_action(current_user, decision_id)
    action_review_service.transition_action.return_value = action

    response = await client.post(
        f"{base_path(workspace_id, decision_id)}/actions/{action.id}/transitions",
        json={"status": "in_progress"},
    )

    assert response.status_code == 200


async def test_schedule_list_and_cancel_review(
    client: AsyncClient,
    current_user: User,
    action_review_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    decision_id = uuid4()
    review = make_review(current_user, decision_id)
    action_review_service.create_review.return_value = review
    action_review_service.list_reviews.return_value = [review]
    action_review_service.cancel_review.return_value = review
    path = f"{base_path(workspace_id, decision_id)}/reviews"

    create_response = await client.post(
        path,
        json={
            "scheduled_for": review.scheduled_for.isoformat(),
            "notes": review.notes,
        },
    )
    list_response = await client.get(path)
    cancel_response = await client.post(f"{path}/{review.id}/cancel")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["status"] == "scheduled"
    assert cancel_response.status_code == 200


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            ActionAssigneeInvalidError(),
            422,
            "The assignee must be an eligible workspace participant",
        ),
        (
            ReviewConflictError(),
            409,
            "The decision already has a scheduled review",
        ),
    ],
)
async def test_action_review_errors_are_mapped(
    error: Exception,
    status_code: int,
    detail: str,
    client: AsyncClient,
    action_review_service: AsyncMock,
) -> None:
    action_review_service.create_action.side_effect = error

    response = await client.post(
        f"{base_path(uuid4(), uuid4())}/actions",
        json={"title": "Deploy the service", "assignee_id": str(uuid4())},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
