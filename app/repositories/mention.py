from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.decision import Decision
from app.models.mention import Mention
from app.models.notification import Notification, NotificationKind, NotificationStatus
from app.models.objection import Objection
from app.models.proposal import Proposal
from app.models.user import User


@dataclass(frozen=True, slots=True)
class MentionRecord:
    mention: Mention
    comment: Comment
    actor: User
    decision: Decision
    proposal: Proposal | None
    objection: Objection | None


class MentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync_for_comment(
        self,
        comment: Comment,
        *,
        mentioned_by: User,
        mentioned_user_ids: set[UUID],
        at: datetime,
        action_url: str,
        excerpt: str,
    ) -> None:
        statement = select(Mention).where(Mention.comment_id == comment.id)
        existing = {
            mention.mentioned_user_id: mention
            for mention in (await self._session.scalars(statement)).all()
        }
        active_ids = {
            user_id for user_id, mention in existing.items() if mention.deleted_at is None
        }

        for user_id in active_ids - mentioned_user_ids:
            removed_mention = existing[user_id]
            removed_mention.deleted_at = at
            removed_mention.read_at = at
            await self._delete_notification(removed_mention.id)

        for user_id in mentioned_user_ids - active_ids:
            current_mention = existing.get(user_id)
            if current_mention is None:
                current_mention = Mention(
                    workspace_id=comment.workspace_id,
                    comment_id=comment.id,
                    mentioned_user_id=user_id,
                    mentioned_by_id=mentioned_by.id,
                    decision_id=comment.decision_id,
                    proposal_id=comment.proposal_id,
                    objection_id=comment.objection_id,
                    created_at=at,
                )
                self._session.add(current_mention)
                await self._session.flush()
            else:
                current_mention.mentioned_by_id = mentioned_by.id
                current_mention.proposal_id = comment.proposal_id
                current_mention.objection_id = comment.objection_id
                current_mention.created_at = at
                current_mention.read_at = None
                current_mention.deleted_at = None
            self._session.add(
                Notification(
                    recipient_id=user_id,
                    workspace_id=comment.workspace_id,
                    kind=NotificationKind.MENTION,
                    source_id=current_mention.id,
                    idempotency_key=f"mention:{current_mention.id}",
                    title=f"{mentioned_by.display_name} mentioned you",
                    body=excerpt,
                    status=NotificationStatus.DELIVERED,
                    attempt_count=0,
                    max_attempts=1,
                    available_at=at,
                    delivered_at=at,
                    actor_id=mentioned_by.id,
                    entity_type="comment",
                    entity_id=comment.id,
                    action_url=action_url,
                )
            )

    async def remove_all_for_comment(self, comment_id: UUID, at: datetime) -> None:
        mentions = list(
            (
                await self._session.scalars(
                    select(Mention).where(
                        Mention.comment_id == comment_id,
                        Mention.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        for mention in mentions:
            mention.deleted_at = at
            mention.read_at = at
            await self._delete_notification(mention.id)

    async def _delete_notification(self, mention_id: UUID) -> None:
        await self._session.execute(
            delete(Notification).where(
                Notification.kind == NotificationKind.MENTION,
                Notification.source_id == mention_id,
            )
        )

    async def list_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        unread_only: bool,
        limit: int,
        cursor_created_at: datetime | None,
        cursor_id: UUID | None,
    ) -> tuple[list[MentionRecord], bool]:
        filters = [
            Mention.workspace_id == workspace_id,
            Mention.mentioned_user_id == user_id,
            Mention.deleted_at.is_(None),
            Comment.deleted_at.is_(None),
        ]
        if unread_only:
            filters.append(Mention.read_at.is_(None))
        if cursor_created_at is not None and cursor_id is not None:
            filters.append(
                or_(
                    Mention.created_at < cursor_created_at,
                    and_(
                        Mention.created_at == cursor_created_at,
                        Mention.id < cursor_id,
                    ),
                )
            )
        statement = (
            select(Mention, Comment, User, Decision, Proposal, Objection)
            .join(Comment, Comment.id == Mention.comment_id)
            .join(User, User.id == Mention.mentioned_by_id)
            .join(Decision, Decision.id == Mention.decision_id)
            .outerjoin(Proposal, Proposal.id == Mention.proposal_id)
            .outerjoin(Objection, Objection.id == Mention.objection_id)
            .where(*filters)
            .order_by(Mention.created_at.desc(), Mention.id.desc())
            .limit(limit + 1)
        )
        rows = (await self._session.execute(statement)).all()
        has_more = len(rows) > limit
        return (
            [
                MentionRecord(
                    mention=row[0],
                    comment=row[1],
                    actor=row[2],
                    decision=row[3],
                    proposal=row[4],
                    objection=row[5],
                )
                for row in rows[:limit]
            ],
            has_more,
        )

    async def unread_count(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        filters = [
            Mention.mentioned_user_id == user_id,
            Mention.read_at.is_(None),
            Mention.deleted_at.is_(None),
            Comment.deleted_at.is_(None),
        ]
        if workspace_id is not None:
            filters.append(Mention.workspace_id == workspace_id)
        statement = (
            select(func.count(Mention.id))
            .join(Comment, Comment.id == Mention.comment_id)
            .where(*filters)
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_owned(
        self,
        workspace_id: UUID,
        mention_id: UUID,
        user_id: UUID,
    ) -> Mention | None:
        statement = select(Mention).where(
            Mention.id == mention_id,
            Mention.workspace_id == workspace_id,
            Mention.mentioned_user_id == user_id,
            Mention.deleted_at.is_(None),
        )
        return cast(Mention | None, await self._session.scalar(statement))

    async def set_read(self, mention: Mention, read_at: datetime | None) -> Mention:
        mention.read_at = read_at
        await self._session.execute(
            update(Notification)
            .where(
                Notification.kind == NotificationKind.MENTION,
                Notification.source_id == mention.id,
                Notification.recipient_id == mention.mentioned_user_id,
            )
            .values(read_at=read_at)
        )
        await self._session.commit()
        await self._session.refresh(mention)
        return mention

    async def mark_all_read(self, workspace_id: UUID, user_id: UUID, at: datetime) -> int:
        mention_ids = list(
            (
                await self._session.scalars(
                    select(Mention.id).where(
                        Mention.workspace_id == workspace_id,
                        Mention.mentioned_user_id == user_id,
                        Mention.read_at.is_(None),
                        Mention.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        if not mention_ids:
            return 0
        result = cast(
            object,
            await self._session.execute(
                update(Mention).where(Mention.id.in_(mention_ids)).values(read_at=at)
            ),
        )
        await self._session.execute(
            update(Notification)
            .where(
                Notification.kind == NotificationKind.MENTION,
                Notification.source_id.in_(mention_ids),
                Notification.recipient_id == user_id,
            )
            .values(read_at=at)
        )
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
