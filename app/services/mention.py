import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import (
    MentionCursorInvalidError,
    MentionNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.mention import Mention
from app.models.user import User
from app.repositories.mention import MentionRecord, MentionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.mention import (
    MentionActorResponse,
    MentionContextResponse,
    MentionListResponse,
    MentionResponse,
    MentionStatus,
)


class MentionService:
    def __init__(
        self,
        mentions: MentionRepository,
        workspaces: WorkspaceRepository,
    ) -> None:
        self._mentions = mentions
        self._workspaces = workspaces

    async def list_mentions(
        self,
        current_user: User,
        workspace_id: UUID,
        *,
        status: MentionStatus,
        limit: int,
        cursor: str | None,
    ) -> MentionListResponse:
        await self._require_membership(current_user.id, workspace_id)
        cursor_created_at, cursor_id = self._decode_cursor(cursor)
        records, has_more = await self._mentions.list_for_user(
            workspace_id,
            current_user.id,
            unread_only=status is MentionStatus.UNREAD,
            limit=limit,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        unread_count = await self._mentions.unread_count(current_user.id, workspace_id)
        next_cursor = None
        if has_more and records:
            final = records[-1].mention
            next_cursor = self._encode_cursor(final.created_at, final.id)
        return MentionListResponse(
            items=[self._response(record) for record in records],
            unread_count=unread_count,
            next_cursor=next_cursor,
        )

    async def mark_read(
        self,
        current_user: User,
        workspace_id: UUID,
        mention_id: UUID,
    ) -> Mention:
        return await self._set_read(current_user, workspace_id, mention_id, datetime.now(UTC))

    async def mark_unread(
        self,
        current_user: User,
        workspace_id: UUID,
        mention_id: UUID,
    ) -> Mention:
        return await self._set_read(current_user, workspace_id, mention_id, None)

    async def mark_all_read(self, current_user: User, workspace_id: UUID) -> int:
        await self._require_membership(current_user.id, workspace_id)
        return await self._mentions.mark_all_read(
            workspace_id,
            current_user.id,
            datetime.now(UTC),
        )

    async def unread_count(self, current_user: User) -> int:
        return await self._mentions.unread_count(current_user.id)

    async def _set_read(
        self,
        current_user: User,
        workspace_id: UUID,
        mention_id: UUID,
        read_at: datetime | None,
    ) -> Mention:
        await self._require_membership(current_user.id, workspace_id)
        mention = await self._mentions.get_owned(workspace_id, mention_id, current_user.id)
        if mention is None:
            raise MentionNotFoundError
        return await self._mentions.set_read(mention, read_at)

    async def _require_membership(self, user_id: UUID, workspace_id: UUID) -> None:
        if await self._workspaces.get_by_id(workspace_id) is None:
            raise WorkspaceNotFoundError
        if await self._workspaces.get_membership(workspace_id, user_id) is None:
            raise WorkspaceNotFoundError

    @staticmethod
    def _response(record: MentionRecord) -> MentionResponse:
        if record.objection is not None:
            context_type = "objection_comment"
        elif record.proposal is not None:
            context_type = "proposal_comment"
        else:
            context_type = "decision_comment"
        return MentionResponse(
            id=record.mention.id,
            workspace_id=record.mention.workspace_id,
            comment_id=record.comment.id,
            mentioned_by=MentionActorResponse(
                id=record.actor.id,
                display_name=record.actor.display_name,
                avatar_url=record.actor.avatar_url,
            ),
            excerpt=CommentExcerpt.make(record.comment.body),
            context=MentionContextResponse(
                type=context_type,
                decision_id=record.decision.id,
                decision_title=record.decision.title,
                proposal_id=record.proposal.id if record.proposal else None,
                proposal_title=record.proposal.title if record.proposal else None,
                objection_id=record.objection.id if record.objection else None,
                objection_title=record.objection.title if record.objection else None,
            ),
            href=(
                f"/w/{record.mention.workspace_id}/decisions/{record.mention.decision_id}"
                f"?comment={record.comment.id}"
            ),
            created_at=record.mention.created_at,
            read_at=record.mention.read_at,
        )

    @staticmethod
    def _encode_cursor(created_at: datetime, mention_id: UUID) -> str:
        raw = json.dumps(
            {"created_at": created_at.isoformat(), "id": str(mention_id)},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(raw).decode()

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
        if cursor is None:
            return None, None
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            created_at = datetime.fromisoformat(payload["created_at"])
            mention_id = UUID(payload["id"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise MentionCursorInvalidError from error
        if created_at.tzinfo is None:
            raise MentionCursorInvalidError
        return created_at, mention_id


class CommentExcerpt:
    @staticmethod
    def make(body: str) -> str:
        normalized = " ".join(body.split())
        return normalized if len(normalized) <= 180 else f"{normalized[:177]}..."
