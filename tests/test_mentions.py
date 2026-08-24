from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import MentionCursorInvalidError, MentionNotFoundError
from app.dependencies.auth import get_current_user
from app.dependencies.mention import get_mention_service
from app.main import app
from app.models.comment import Comment
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.mention import Mention
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.mention import MentionRecord
from app.schemas.mention import MentionListResponse, MentionStatus
from app.services.mention import MentionService


def make_user(name: str = "Raman Singh") -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email=f"{uuid4()}@example.com",
        password_hash="hash",
        display_name=name,
        avatar_url=None,
        is_active=True,
        is_email_verified=True,
        auth_version=0,
        created_at=now,
        updated_at=now,
    )


def mention_record(recipient: User, actor: User) -> MentionRecord:
    now = datetime.now(UTC)
    workspace_id = uuid4()
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by_id=actor.id,
        title="Authentication strategy",
        category=DecisionCategory.ARCHITECTURE,
        status=DecisionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    comment = Comment(
        id=uuid4(),
        workspace_id=workspace_id,
        decision_id=decision.id,
        author_id=actor.id,
        body="Can you review this evidence before voting?",
        structured_body={"content": [{"type": "text", "text": "Review"}]},
        created_at=now,
        updated_at=now,
    )
    mention = Mention(
        id=uuid4(),
        workspace_id=workspace_id,
        comment_id=comment.id,
        mentioned_user_id=recipient.id,
        mentioned_by_id=actor.id,
        decision_id=decision.id,
        created_at=now,
    )
    return MentionRecord(mention, comment, actor, decision, None, None)


def configured_service(user: User) -> tuple[MentionService, Mock, Mock]:
    workspace_id = uuid4()
    workspaces = Mock()
    workspaces.get_by_id = AsyncMock(
        return_value=Workspace(id=workspace_id, name="Auth", owner_id=user.id)
    )
    workspaces.get_membership = AsyncMock(
        return_value=WorkspaceMember(
            id=uuid4(),
            workspace_id=workspace_id,
            user_id=user.id,
            role=WorkspaceRole.MEMBER,
        )
    )
    mentions = Mock()
    mentions.list_for_user = AsyncMock(return_value=([], False))
    mentions.unread_count = AsyncMock(return_value=0)
    mentions.get_owned = AsyncMock(return_value=None)
    mentions.set_read = AsyncMock()
    mentions.mark_all_read = AsyncMock(return_value=0)
    return MentionService(mentions, workspaces), mentions, workspaces


@pytest.mark.asyncio
async def test_list_mentions_is_scoped_to_current_user() -> None:
    user = make_user()
    service, mentions, workspaces = configured_service(user)
    workspace_id = workspaces.get_by_id.return_value.id

    await service.list_mentions(
        user,
        workspace_id,
        status=MentionStatus.ALL,
        limit=30,
        cursor=None,
    )

    assert mentions.list_for_user.await_args.args[:2] == (workspace_id, user.id)


@pytest.mark.asyncio
async def test_unread_filter_is_forwarded() -> None:
    user = make_user()
    service, mentions, workspaces = configured_service(user)

    await service.list_mentions(
        user,
        workspaces.get_by_id.return_value.id,
        status=MentionStatus.UNREAD,
        limit=30,
        cursor=None,
    )

    assert mentions.list_for_user.await_args.kwargs["unread_only"] is True


@pytest.mark.asyncio
async def test_cursor_pagination_returns_opaque_next_cursor() -> None:
    user = make_user()
    actor = make_user("Aman")
    record = mention_record(user, actor)
    service, mentions, workspaces = configured_service(user)
    workspace_id = record.mention.workspace_id
    workspaces.get_by_id.return_value.id = workspace_id
    workspaces.get_membership.return_value.workspace_id = workspace_id
    mentions.list_for_user.return_value = ([record], True)

    result = await service.list_mentions(
        user,
        workspace_id,
        status=MentionStatus.ALL,
        limit=1,
        cursor=None,
    )

    assert result.next_cursor is not None
    assert str(record.mention.id) not in result.next_cursor


@pytest.mark.asyncio
async def test_invalid_cursor_is_rejected() -> None:
    user = make_user()
    service, _, workspaces = configured_service(user)

    with pytest.raises(MentionCursorInvalidError):
        await service.list_mentions(
            user,
            workspaces.get_by_id.return_value.id,
            status=MentionStatus.ALL,
            limit=30,
            cursor="not-a-cursor",
        )


@pytest.mark.asyncio
async def test_user_cannot_mark_another_users_mention_read() -> None:
    user = make_user()
    service, _, workspaces = configured_service(user)

    with pytest.raises(MentionNotFoundError):
        await service.mark_read(user, workspaces.get_by_id.return_value.id, uuid4())


@pytest.mark.asyncio
async def test_mark_read_and_unread() -> None:
    user = make_user()
    service, mentions, workspaces = configured_service(user)
    record = mention_record(user, make_user("Aman"))
    mentions.get_owned.return_value = record.mention
    mentions.set_read.side_effect = lambda mention, read_at: mention

    await service.mark_read(user, workspaces.get_by_id.return_value.id, record.mention.id)
    assert mentions.set_read.await_args.args[1] is not None
    await service.mark_unread(user, workspaces.get_by_id.return_value.id, record.mention.id)
    assert mentions.set_read.await_args.args[1] is None


@pytest.mark.asyncio
async def test_mark_all_read_is_workspace_scoped() -> None:
    user = make_user()
    service, mentions, workspaces = configured_service(user)
    workspace_id = workspaces.get_by_id.return_value.id
    mentions.mark_all_read.return_value = 4

    assert await service.mark_all_read(user, workspace_id) == 4
    mentions.mark_all_read.assert_awaited_once()


@pytest.mark.asyncio
async def test_global_unread_count() -> None:
    user = make_user()
    service, mentions, _ = configured_service(user)
    mentions.unread_count.return_value = 7

    assert await service.unread_count(user) == 7
    mentions.unread_count.assert_awaited_once_with(user.id)


@pytest.fixture
def mention_api_overrides() -> tuple[User, Mock]:
    user = make_user()
    service = Mock()
    service.list_mentions = AsyncMock(
        return_value=MentionListResponse(items=[], unread_count=2, next_cursor=None)
    )
    service.mark_all_read = AsyncMock(return_value=2)
    service.unread_count = AsyncMock(return_value=3)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_mention_service] = lambda: service
    yield user, service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_mentions_api(
    client: AsyncClient,
    mention_api_overrides: tuple[User, Mock],
) -> None:
    response = await client.get(f"/api/v1/workspaces/{uuid4()}/mentions?status=unread")

    assert response.status_code == 200
    assert response.json() == {"items": [], "unread_count": 2, "next_cursor": None}


@pytest.mark.asyncio
async def test_global_unread_count_api(
    client: AsyncClient,
    mention_api_overrides: tuple[User, Mock],
) -> None:
    response = await client.get("/api/v1/mentions/unread-count")

    assert response.status_code == 200
    assert response.json() == {"count": 3}


@pytest.mark.asyncio
async def test_mark_all_read_api(
    client: AsyncClient,
    mention_api_overrides: tuple[User, Mock],
) -> None:
    response = await client.post(f"/api/v1/workspaces/{uuid4()}/mentions/read-all")

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
