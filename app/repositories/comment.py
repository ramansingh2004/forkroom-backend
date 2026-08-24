from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.decision import Decision
from app.models.objection import Objection
from app.models.proposal import Proposal
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


@dataclass(frozen=True, slots=True)
class CommentRecord:
    comment: Comment
    author: User


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        return await self._session.get(Workspace, workspace_id)

    async def get_membership(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceMember | None:
        statement = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        return cast(WorkspaceMember | None, await self._session.scalar(statement))

    async def get_decision(self, workspace_id: UUID, decision_id: UUID) -> Decision | None:
        statement = select(Decision).where(
            Decision.id == decision_id,
            Decision.workspace_id == workspace_id,
        )
        return cast(Decision | None, await self._session.scalar(statement))

    async def proposal_belongs_to_decision(
        self,
        proposal_id: UUID,
        decision_id: UUID,
    ) -> bool:
        statement = select(Proposal.id).where(
            Proposal.id == proposal_id,
            Proposal.decision_id == decision_id,
        )
        return await self._session.scalar(statement) is not None

    async def objection_belongs_to_decision(
        self,
        objection_id: UUID,
        decision_id: UUID,
    ) -> bool:
        statement = (
            select(Objection.id)
            .join(Proposal, Proposal.id == Objection.proposal_id)
            .where(
                Objection.id == objection_id,
                Proposal.decision_id == decision_id,
            )
        )
        return await self._session.scalar(statement) is not None

    async def active_workspace_users(
        self,
        workspace_id: UUID,
        user_ids: set[UUID],
    ) -> dict[UUID, User]:
        if not user_ids:
            return {}
        statement = (
            select(User)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                User.id.in_(user_ids),
                User.is_active.is_(True),
            )
        )
        users = list((await self._session.scalars(statement)).all())
        return {user.id: user for user in users}

    async def add(self, comment: Comment) -> Comment:
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def get_record(
        self,
        workspace_id: UUID,
        comment_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> CommentRecord | None:
        filters = [
            Comment.id == comment_id,
            Comment.workspace_id == workspace_id,
        ]
        if not include_deleted:
            filters.append(Comment.deleted_at.is_(None))
        statement = select(Comment, User).join(User, User.id == Comment.author_id).where(*filters)
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return CommentRecord(comment=row[0], author=row[1])

    async def list_for_decision(
        self,
        workspace_id: UUID,
        decision_id: UUID,
        *,
        proposal_id: UUID | None,
        objection_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[CommentRecord]:
        filters = [
            Comment.workspace_id == workspace_id,
            Comment.decision_id == decision_id,
            Comment.deleted_at.is_(None),
        ]
        if proposal_id is not None:
            filters.append(Comment.proposal_id == proposal_id)
        if objection_id is not None:
            filters.append(Comment.objection_id == objection_id)
        statement = (
            select(Comment, User)
            .join(User, User.id == Comment.author_id)
            .where(*filters)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return [
            CommentRecord(comment=row[0], author=row[1])
            for row in (await self._session.execute(statement)).all()
        ]

    async def commit(self, comment: Comment) -> None:
        await self._session.commit()
        await self._session.refresh(comment)

    async def rollback(self) -> None:
        await self._session.rollback()

    def update(
        self,
        comment: Comment,
        *,
        body: str,
        structured_body: dict[str, object],
    ) -> None:
        comment.body = body
        comment.structured_body = structured_body

    def soft_delete(self, comment: Comment, at: datetime) -> None:
        comment.deleted_at = at
