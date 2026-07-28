from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WorkspaceMemberAlreadyExistsError
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole


@dataclass(frozen=True, slots=True)
class WorkspaceMemberRecord:
    membership: WorkspaceMember
    user: User


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, workspace: Workspace) -> Workspace:
        self._session.add(workspace)
        await self._session.flush()
        self._session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=workspace.owner_id,
                role=WorkspaceRole.OWNER,
            )
        )
        await self._session.commit()
        await self._session.refresh(workspace)
        return workspace

    async def list_for_user(self, user_id: UUID) -> list[Workspace]:
        statement = (
            select(Workspace)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
            )
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.updated_at.desc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
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
        return cast(
            WorkspaceMember | None,
            await self._session.scalar(statement),
        )

    async def update(
        self,
        workspace: Workspace,
        *,
        name: str | None,
        description: str | None,
        update_name: bool,
        update_description: bool,
    ) -> Workspace:
        if update_name and name is not None:
            workspace.name = name
        if update_description:
            workspace.description = description
        await self._session.commit()
        await self._session.refresh(workspace)
        return workspace

    async def delete(self, workspace: Workspace) -> None:
        await self._session.delete(workspace)
        await self._session.commit()

    async def list_members(self, workspace_id: UUID) -> list[WorkspaceMemberRecord]:
        statement = (
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.joined_at.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return [
            WorkspaceMemberRecord(
                membership=row[0],
                user=row[1],
            )
            for row in rows
        ]

    async def list_voting_eligible_user_ids(self, workspace_id: UUID) -> list[UUID]:
        statement = (
            select(WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role.in_(
                    {
                        WorkspaceRole.OWNER,
                        WorkspaceRole.ADMIN,
                        WorkspaceRole.MEMBER,
                    }
                ),
            )
            .order_by(WorkspaceMember.joined_at.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        role: WorkspaceRole,
    ) -> WorkspaceMember:
        membership = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )
        self._session.add(membership)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise WorkspaceMemberAlreadyExistsError from error
        await self._session.refresh(membership)
        return membership

    async def update_member_role(
        self,
        membership: WorkspaceMember,
        role: WorkspaceRole,
    ) -> WorkspaceMember:
        membership.role = role
        await self._session.commit()
        await self._session.refresh(membership)
        return membership

    async def remove_member(self, membership: WorkspaceMember) -> None:
        statement = delete(WorkspaceMember).where(
            WorkspaceMember.id == membership.id,
        )
        await self._session.execute(statement)
        await self._session.commit()
