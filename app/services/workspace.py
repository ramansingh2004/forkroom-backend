from uuid import UUID

from app.core.exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceMemberAlreadyExistsError,
    WorkspaceMemberNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceOwnerImmutableError,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.permissions.workspace import (
    can_change_member_role,
    can_delete_workspace,
    can_manage_workspace,
    can_remove_member,
)
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceMemberRecord, WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceUpdateRequest,
)


class WorkspaceService:
    def __init__(
        self,
        workspace_repository: WorkspaceRepository,
        user_repository: UserRepository,
    ) -> None:
        self._workspaces = workspace_repository
        self._users = user_repository

    async def create(
        self,
        current_user: User,
        payload: WorkspaceCreateRequest,
    ) -> Workspace:
        return await self._workspaces.create(
            Workspace(
                name=payload.name,
                description=payload.description,
                owner_id=current_user.id,
            )
        )

    async def list_workspaces(self, current_user: User) -> list[Workspace]:
        return await self._workspaces.list_for_user(current_user.id)

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
    ) -> Workspace:
        workspace, _ = await self._require_membership(current_user.id, workspace_id)
        return workspace

    async def update(
        self,
        current_user: User,
        workspace_id: UUID,
        payload: WorkspaceUpdateRequest,
    ) -> Workspace:
        workspace, membership = await self._require_membership(
            current_user.id,
            workspace_id,
        )
        if not can_manage_workspace(membership.role):
            raise WorkspaceAccessDeniedError

        provided_fields = payload.model_fields_set
        return await self._workspaces.update(
            workspace,
            name=payload.name,
            description=payload.description,
            update_name="name" in provided_fields,
            update_description="description" in provided_fields,
        )

    async def delete(
        self,
        current_user: User,
        workspace_id: UUID,
    ) -> None:
        workspace, membership = await self._require_membership(
            current_user.id,
            workspace_id,
        )
        if not can_delete_workspace(membership.role):
            raise WorkspaceAccessDeniedError
        await self._workspaces.delete(workspace)

    async def list_members(
        self,
        current_user: User,
        workspace_id: UUID,
    ) -> list[WorkspaceMemberRecord]:
        await self._require_membership(current_user.id, workspace_id)
        return await self._workspaces.list_members(workspace_id)

    async def add_member(
        self,
        current_user: User,
        workspace_id: UUID,
        payload: WorkspaceMemberCreateRequest,
    ) -> WorkspaceMemberRecord:
        _, actor_membership = await self._require_membership(
            current_user.id,
            workspace_id,
        )
        if not can_manage_workspace(actor_membership.role):
            raise WorkspaceAccessDeniedError

        user = await self._users.get_by_email(payload.email.lower())
        if user is None or not user.is_active:
            raise WorkspaceMemberNotFoundError

        try:
            membership = await self._workspaces.add_member(
                workspace_id,
                user.id,
                WorkspaceRole(payload.role.value),
            )
        except WorkspaceMemberAlreadyExistsError:
            raise
        return WorkspaceMemberRecord(
            membership=membership,
            user=user,
        )

    async def update_member_role(
        self,
        current_user: User,
        workspace_id: UUID,
        member_user_id: UUID,
        payload: WorkspaceMemberUpdateRequest,
    ) -> WorkspaceMemberRecord:
        _, actor_membership = await self._require_membership(
            current_user.id,
            workspace_id,
        )
        target_membership = await self._require_member(
            workspace_id,
            member_user_id,
        )
        if target_membership.role is WorkspaceRole.OWNER:
            raise WorkspaceOwnerImmutableError
        if not can_change_member_role(
            actor_membership.role,
            target_membership.role,
        ):
            raise WorkspaceAccessDeniedError

        user = await self._users.get_by_id(member_user_id)
        if user is None:
            raise WorkspaceMemberNotFoundError
        membership = await self._workspaces.update_member_role(
            target_membership,
            WorkspaceRole(payload.role.value),
        )
        return WorkspaceMemberRecord(
            membership=membership,
            user=user,
        )

    async def remove_member(
        self,
        current_user: User,
        workspace_id: UUID,
        member_user_id: UUID,
    ) -> None:
        _, actor_membership = await self._require_membership(
            current_user.id,
            workspace_id,
        )
        target_membership = await self._require_member(
            workspace_id,
            member_user_id,
        )
        if target_membership.role is WorkspaceRole.OWNER:
            raise WorkspaceOwnerImmutableError
        if not can_remove_member(
            actor_membership.role,
            target_membership.role,
        ):
            raise WorkspaceAccessDeniedError
        await self._workspaces.remove_member(target_membership)

    async def _require_membership(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> tuple[Workspace, WorkspaceMember]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(
            workspace_id,
            user_id,
        )
        if membership is None:
            raise WorkspaceNotFoundError
        return workspace, membership

    async def _require_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceMember:
        membership = await self._workspaces.get_membership(
            workspace_id,
            user_id,
        )
        if membership is None:
            raise WorkspaceMemberNotFoundError
        return membership
