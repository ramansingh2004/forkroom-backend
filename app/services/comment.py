from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import (
    CommentAccessDeniedError,
    CommentContextInvalidError,
    CommentNotFoundError,
    DecisionNotFoundError,
    MentionMemberInvalidError,
    WorkspaceNotFoundError,
)
from app.models.comment import Comment
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.repositories.comment import CommentRecord, CommentRepository
from app.repositories.mention import MentionRepository
from app.schemas.comment import (
    CommentCreateRequest,
    CommentMentionNode,
    CommentUpdateRequest,
    StructuredCommentBody,
)


class CommentService:
    def __init__(
        self,
        comments: CommentRepository,
        mentions: MentionRepository,
    ) -> None:
        self._comments = comments
        self._mentions = mentions

    async def list_comments(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        *,
        proposal_id: UUID | None,
        objection_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[CommentRecord]:
        await self._require_membership(current_user.id, workspace_id)
        await self._require_decision(workspace_id, decision_id)
        await self._validate_context(decision_id, proposal_id, objection_id)
        return await self._comments.list_for_decision(
            workspace_id,
            decision_id,
            proposal_id=proposal_id,
            objection_id=objection_id,
            limit=limit,
            offset=offset,
        )

    async def create(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: CommentCreateRequest,
    ) -> CommentRecord:
        await self._require_membership(current_user.id, workspace_id)
        await self._require_decision(workspace_id, decision_id)
        await self._validate_context(decision_id, payload.proposal_id, payload.objection_id)
        mentioned_user_ids = self._mentioned_user_ids(payload.structured_body)
        users = await self._validate_mentioned_users(workspace_id, mentioned_user_ids)
        structured_body = self._canonical_structured_body(payload.structured_body, users)
        comment = Comment(
            workspace_id=workspace_id,
            decision_id=decision_id,
            proposal_id=payload.proposal_id,
            objection_id=payload.objection_id,
            author_id=current_user.id,
            body=payload.body.strip(),
            structured_body=structured_body,
        )
        try:
            await self._comments.add(comment)
            await self._mentions.sync_for_comment(
                comment,
                mentioned_by=current_user,
                mentioned_user_ids=mentioned_user_ids,
                at=datetime.now(UTC),
                action_url=self._action_url(comment),
                excerpt=self._excerpt(comment.body),
            )
            await self._comments.commit(comment)
        except Exception:
            await self._comments.rollback()
            raise
        record = await self._comments.get_record(workspace_id, comment.id)
        if record is None:
            raise CommentNotFoundError
        return record

    async def update(
        self,
        current_user: User,
        workspace_id: UUID,
        comment_id: UUID,
        payload: CommentUpdateRequest,
    ) -> CommentRecord:
        membership = await self._require_membership(current_user.id, workspace_id)
        record = await self._require_comment(workspace_id, comment_id)
        if record.comment.author_id != current_user.id and membership.role not in {
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
        }:
            raise CommentAccessDeniedError
        mentioned_user_ids = self._mentioned_user_ids(payload.structured_body)
        users = await self._validate_mentioned_users(workspace_id, mentioned_user_ids)
        structured_body = self._canonical_structured_body(payload.structured_body, users)
        try:
            self._comments.update(
                record.comment,
                body=payload.body.strip(),
                structured_body=structured_body,
            )
            await self._mentions.sync_for_comment(
                record.comment,
                mentioned_by=record.author,
                mentioned_user_ids=mentioned_user_ids,
                at=datetime.now(UTC),
                action_url=self._action_url(record.comment),
                excerpt=self._excerpt(payload.body),
            )
            await self._comments.commit(record.comment)
        except Exception:
            await self._comments.rollback()
            raise
        return record

    async def delete(
        self,
        current_user: User,
        workspace_id: UUID,
        comment_id: UUID,
    ) -> None:
        membership = await self._require_membership(current_user.id, workspace_id)
        record = await self._require_comment(workspace_id, comment_id)
        if record.comment.author_id != current_user.id and membership.role not in {
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
        }:
            raise CommentAccessDeniedError
        at = datetime.now(UTC)
        try:
            self._comments.soft_delete(record.comment, at)
            await self._mentions.remove_all_for_comment(record.comment.id, at)
            await self._comments.commit(record.comment)
        except Exception:
            await self._comments.rollback()
            raise

    async def _require_membership(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceMember:
        if await self._comments.get_workspace(workspace_id) is None:
            raise WorkspaceNotFoundError
        membership = await self._comments.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        return membership

    async def _require_decision(self, workspace_id: UUID, decision_id: UUID) -> None:
        if await self._comments.get_decision(workspace_id, decision_id) is None:
            raise DecisionNotFoundError

    async def _require_comment(self, workspace_id: UUID, comment_id: UUID) -> CommentRecord:
        record = await self._comments.get_record(workspace_id, comment_id)
        if record is None:
            raise CommentNotFoundError
        return record

    async def _validate_context(
        self,
        decision_id: UUID,
        proposal_id: UUID | None,
        objection_id: UUID | None,
    ) -> None:
        if proposal_id is not None and objection_id is not None:
            raise CommentContextInvalidError
        if proposal_id is not None and not await self._comments.proposal_belongs_to_decision(
            proposal_id, decision_id
        ):
            raise CommentContextInvalidError
        if objection_id is not None and not await self._comments.objection_belongs_to_decision(
            objection_id, decision_id
        ):
            raise CommentContextInvalidError

    async def _validate_mentioned_users(
        self,
        workspace_id: UUID,
        user_ids: set[UUID],
    ) -> dict[UUID, User]:
        users = await self._comments.active_workspace_users(workspace_id, user_ids)
        if set(users) != user_ids:
            raise MentionMemberInvalidError
        return users

    @staticmethod
    def _mentioned_user_ids(structured_body: StructuredCommentBody) -> set[UUID]:
        return {
            node.user_id for node in structured_body.content if isinstance(node, CommentMentionNode)
        }

    @staticmethod
    def _canonical_structured_body(
        structured_body: StructuredCommentBody,
        users: dict[UUID, User],
    ) -> dict[str, object]:
        content: list[dict[str, object]] = []
        for node in structured_body.content:
            if isinstance(node, CommentMentionNode):
                content.append(
                    {
                        "type": "mention",
                        "user_id": str(node.user_id),
                        "label": users[node.user_id].display_name,
                    }
                )
            else:
                content.append({"type": "text", "text": node.text})
        return {"content": content}

    @staticmethod
    def _action_url(comment: Comment) -> str:
        return f"/w/{comment.workspace_id}/decisions/{comment.decision_id}?comment={comment.id}"

    @staticmethod
    def _excerpt(body: str) -> str:
        normalized = " ".join(body.split())
        return normalized if len(normalized) <= 180 else f"{normalized[:177]}..."
