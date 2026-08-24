from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.auth import get_current_user
from app.dependencies.comment import get_comment_service
from app.main import app
from app.models.comment import Comment
from app.models.user import User
from app.repositories.comment import CommentRecord


def make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        avatar_url=None,
        is_active=True,
        is_email_verified=True,
        auth_version=0,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def comment_api_overrides() -> tuple[User, Comment, Mock]:
    user = make_user()
    now = datetime.now(UTC)
    comment = Comment(
        id=uuid4(),
        workspace_id=uuid4(),
        decision_id=uuid4(),
        author_id=user.id,
        body="Please review this evidence.",
        structured_body={"content": [{"type": "text", "text": "Please review."}]},
        created_at=now,
        updated_at=now,
    )
    record = CommentRecord(comment, user)
    service = Mock()
    service.list_comments = AsyncMock(return_value=[record])
    service.create = AsyncMock(return_value=record)
    service.update = AsyncMock(return_value=record)
    service.delete = AsyncMock(return_value=None)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_comment_service] = lambda: service
    yield user, comment, service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_comments_api(
    client: AsyncClient,
    comment_api_overrides: tuple[User, Comment, Mock],
) -> None:
    _, comment, _ = comment_api_overrides
    response = await client.get(
        f"/api/v1/workspaces/{comment.workspace_id}/decisions/{comment.decision_id}/comments"
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(comment.id)


@pytest.mark.asyncio
async def test_create_structured_comment_api(
    client: AsyncClient,
    comment_api_overrides: tuple[User, Comment, Mock],
) -> None:
    user, comment, service = comment_api_overrides
    response = await client.post(
        f"/api/v1/workspaces/{comment.workspace_id}/decisions/{comment.decision_id}/comments",
        json={
            "body": "Please review, @Raman Singh",
            "structured_body": {
                "content": [
                    {"type": "text", "text": "Please review, "},
                    {"type": "mention", "user_id": str(user.id), "label": "Raman Singh"},
                ]
            },
        },
    )

    assert response.status_code == 201
    service.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_comment_api(
    client: AsyncClient,
    comment_api_overrides: tuple[User, Comment, Mock],
) -> None:
    _, comment, service = comment_api_overrides
    response = await client.patch(
        f"/api/v1/workspaces/{comment.workspace_id}/comments/{comment.id}",
        json={
            "body": "Updated",
            "structured_body": {"content": [{"type": "text", "text": "Updated"}]},
        },
    )

    assert response.status_code == 200
    service.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_comment_api(
    client: AsyncClient,
    comment_api_overrides: tuple[User, Comment, Mock],
) -> None:
    _, comment, service = comment_api_overrides
    response = await client.delete(
        f"/api/v1/workspaces/{comment.workspace_id}/comments/{comment.id}"
    )

    assert response.status_code == 204
    service.delete.assert_awaited_once()
