from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import (
    CommentAccessDeniedError,
    DecisionNotFoundError,
    MentionMemberInvalidError,
)
from app.models.comment import Comment
from app.models.mention import Mention
from app.models.notification import Notification, NotificationKind
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.repositories.comment import CommentRecord
from app.repositories.mention import MentionRepository
from app.schemas.comment import CommentCreateRequest, CommentUpdateRequest
from app.services.comment import CommentService


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


def membership(user: User, workspace_id: UUID, role: WorkspaceRole) -> WorkspaceMember:
    return WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=user.id,
        role=role,
        joined_at=datetime.now(UTC),
    )


def create_payload(*user_ids: UUID) -> CommentCreateRequest:
    content: list[dict[str, object]] = [{"type": "text", "text": "Please review, "}]
    content.extend(
        {"type": "mention", "user_id": str(user_id), "label": "Old label"} for user_id in user_ids
    )
    return CommentCreateRequest.model_validate(
        {
            "body": "Please review this evidence.",
            "structured_body": {"content": content},
        }
    )


def configured_comment_service(
    actor: User,
    workspace_id: UUID,
    decision_id: UUID,
) -> tuple[CommentService, Mock, Mock]:
    comments = Mock()
    comments.get_workspace = AsyncMock(return_value=object())
    comments.get_membership = AsyncMock(
        return_value=membership(actor, workspace_id, WorkspaceRole.MEMBER)
    )
    comments.get_decision = AsyncMock(return_value=object())
    comments.proposal_belongs_to_decision = AsyncMock(return_value=True)
    comments.objection_belongs_to_decision = AsyncMock(return_value=True)
    comments.active_workspace_users = AsyncMock(return_value={})
    comments.add = AsyncMock()
    comments.commit = AsyncMock()
    comments.rollback = AsyncMock()
    comments.get_record = AsyncMock()
    comments.list_for_decision = AsyncMock(return_value=[])
    comments.update = Mock()
    comments.soft_delete = Mock()
    mentions = Mock()
    mentions.sync_for_comment = AsyncMock()
    mentions.remove_all_for_comment = AsyncMock()
    return CommentService(comments, mentions), comments, mentions


@pytest.mark.asyncio
async def test_create_comment_mentions_active_workspace_member() -> None:
    actor = make_user("Aman Sharma")
    recipient = make_user()
    workspace_id = uuid4()
    decision_id = uuid4()
    service, comments, mentions = configured_comment_service(actor, workspace_id, decision_id)
    comments.active_workspace_users.return_value = {recipient.id: recipient}

    async def add(comment: Comment) -> Comment:
        comment.id = uuid4()
        return comment

    comments.add.side_effect = add

    async def record(_workspace_id: UUID, _comment_id: UUID) -> CommentRecord:
        created = comments.add.await_args.args[0]
        created.created_at = datetime.now(UTC)
        created.updated_at = datetime.now(UTC)
        return CommentRecord(created, actor)

    comments.get_record.side_effect = record

    result = await service.create(actor, workspace_id, decision_id, create_payload(recipient.id))

    assert result.author is actor
    assert result.comment.structured_body["content"][1]["label"] == "Raman Singh"  # type: ignore[index]
    assert mentions.sync_for_comment.await_args.kwargs["mentioned_user_ids"] == {recipient.id}
    comments.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_comment_rejects_non_member_mention() -> None:
    actor = make_user()
    workspace_id = uuid4()
    service, comments, _ = configured_comment_service(actor, workspace_id, uuid4())
    comments.active_workspace_users.return_value = {}

    with pytest.raises(MentionMemberInvalidError):
        await service.create(actor, workspace_id, uuid4(), create_payload(uuid4()))


@pytest.mark.asyncio
async def test_create_comment_rolls_back_when_mention_sync_fails() -> None:
    actor = make_user()
    workspace_id = uuid4()
    decision_id = uuid4()
    service, comments, mentions = configured_comment_service(actor, workspace_id, decision_id)
    comments.add.side_effect = lambda comment: setattr(comment, "id", uuid4()) or comment
    mentions.sync_for_comment.side_effect = RuntimeError("mention insert failed")

    with pytest.raises(RuntimeError):
        await service.create(actor, workspace_id, decision_id, create_payload())

    comments.rollback.assert_awaited_once()
    comments.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_comments_hides_missing_decision() -> None:
    actor = make_user()
    workspace_id = uuid4()
    service, comments, _ = configured_comment_service(actor, workspace_id, uuid4())
    comments.get_decision.return_value = None

    with pytest.raises(DecisionNotFoundError):
        await service.list_comments(
            actor,
            workspace_id,
            uuid4(),
            proposal_id=None,
            objection_id=None,
            limit=50,
            offset=0,
        )

    comments.list_for_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_comment_edit_requires_author_or_admin() -> None:
    actor = make_user()
    author = make_user("Author")
    workspace_id = uuid4()
    service, comments, _ = configured_comment_service(actor, workspace_id, uuid4())
    comment = Comment(
        id=uuid4(),
        workspace_id=workspace_id,
        decision_id=uuid4(),
        author_id=author.id,
        body="Original",
        structured_body={"content": [{"type": "text", "text": "Original"}]},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    comments.get_record.return_value = CommentRecord(comment, author)
    payload = CommentUpdateRequest.model_validate(
        {"body": "Changed", "structured_body": {"content": [{"type": "text", "text": "Changed"}]}}
    )

    with pytest.raises(CommentAccessDeniedError):
        await service.update(actor, workspace_id, comment.id, payload)


@pytest.mark.asyncio
async def test_comment_delete_allows_workspace_admin() -> None:
    actor = make_user()
    author = make_user("Author")
    workspace_id = uuid4()
    service, comments, mentions = configured_comment_service(actor, workspace_id, uuid4())
    comments.get_membership.return_value = membership(actor, workspace_id, WorkspaceRole.ADMIN)
    comment = Comment(
        id=uuid4(),
        workspace_id=workspace_id,
        decision_id=uuid4(),
        author_id=author.id,
        body="Original",
        structured_body={"content": [{"type": "text", "text": "Original"}]},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    comments.get_record.return_value = CommentRecord(comment, author)

    await service.delete(actor, workspace_id, comment.id)

    comments.soft_delete.assert_called_once()
    mentions.remove_all_for_comment.assert_awaited_once()
    comments.commit.assert_awaited_once()


class ScalarResult:
    def __init__(self, values: list[Mention]) -> None:
        self._values = values

    def all(self) -> list[Mention]:
        return self._values


@pytest.mark.asyncio
async def test_edit_sync_keeps_adds_and_removes_mentions() -> None:
    now = datetime.now(UTC)
    actor = make_user("Aman")
    workspace_id = uuid4()
    decision_id = uuid4()
    comment = Comment(
        id=uuid4(),
        workspace_id=workspace_id,
        decision_id=decision_id,
        author_id=actor.id,
        body="Body",
        structured_body={"content": []},
        created_at=now,
        updated_at=now,
    )
    kept_user_id = uuid4()
    removed_user_id = uuid4()
    added_user_id = uuid4()
    kept = Mention(
        id=uuid4(),
        workspace_id=workspace_id,
        comment_id=comment.id,
        mentioned_user_id=kept_user_id,
        mentioned_by_id=actor.id,
        decision_id=decision_id,
        created_at=now,
    )
    removed = Mention(
        id=uuid4(),
        workspace_id=workspace_id,
        comment_id=comment.id,
        mentioned_user_id=removed_user_id,
        mentioned_by_id=actor.id,
        decision_id=decision_id,
        created_at=now,
    )
    session = Mock()
    session.scalars = AsyncMock(return_value=ScalarResult([kept, removed]))
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    repository = MentionRepository(session)

    await repository.sync_for_comment(
        comment,
        mentioned_by=actor,
        mentioned_user_ids={kept_user_id, added_user_id},
        at=now,
        action_url="/comment",
        excerpt="Body",
    )

    assert kept.deleted_at is None
    assert removed.deleted_at == now
    notifications = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], Notification)
    ]
    assert len(notifications) == 1
    assert notifications[0].recipient_id == added_user_id
    assert notifications[0].kind is NotificationKind.MENTION


def test_duplicate_mention_nodes_are_deduplicated() -> None:
    user_id = uuid4()
    payload = create_payload(user_id, user_id)

    assert CommentService._mentioned_user_ids(payload.structured_body) == {user_id}
