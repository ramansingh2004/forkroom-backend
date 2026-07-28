from uuid import UUID

from fastapi import HTTPException, status

from app.core.exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceMemberAlreadyExistsError,
    WorkspaceMemberNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceOwnerImmutableError,
)
from app.models.user import User
from app.repositories.workspace import WorkspaceMemberRecord
from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.workspace import WorkspaceService


def _member_response(record: WorkspaceMemberRecord) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        user_id=record.user.id,
        email=record.user.email,
        display_name=record.user.display_name,
        avatar_url=record.user.avatar_url,
        role=record.membership.role,
        joined_at=record.membership.joined_at,
    )


def _raise_workspace_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        ) from error
    if isinstance(error, WorkspaceMemberNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found",
        ) from error
    if isinstance(error, WorkspaceMemberAlreadyExistsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a workspace member",
        ) from error
    if isinstance(error, WorkspaceOwnerImmutableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The workspace owner cannot be removed or assigned another role",
        ) from error
    if isinstance(error, WorkspaceAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this workspace action",
        ) from error
    raise error


async def create_workspace(
    payload: WorkspaceCreateRequest,
    current_user: User,
    service: WorkspaceService,
) -> WorkspaceResponse:
    workspace = await service.create(current_user, payload)
    return WorkspaceResponse.model_validate(workspace)


async def list_workspaces(
    current_user: User,
    service: WorkspaceService,
) -> list[WorkspaceResponse]:
    workspaces = await service.list_workspaces(current_user)
    return [WorkspaceResponse.model_validate(workspace) for workspace in workspaces]


async def get_workspace(
    workspace_id: UUID,
    current_user: User,
    service: WorkspaceService,
) -> WorkspaceResponse:
    try:
        workspace = await service.get(current_user, workspace_id)
    except Exception as error:
        _raise_workspace_error(error)
        raise
    return WorkspaceResponse.model_validate(workspace)


async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdateRequest,
    current_user: User,
    service: WorkspaceService,
) -> WorkspaceResponse:
    try:
        workspace = await service.update(
            current_user,
            workspace_id,
            payload,
        )
    except Exception as error:
        _raise_workspace_error(error)
        raise
    return WorkspaceResponse.model_validate(workspace)


async def delete_workspace(
    workspace_id: UUID,
    current_user: User,
    service: WorkspaceService,
) -> None:
    try:
        await service.delete(current_user, workspace_id)
    except Exception as error:
        _raise_workspace_error(error)


async def list_workspace_members(
    workspace_id: UUID,
    current_user: User,
    service: WorkspaceService,
) -> list[WorkspaceMemberResponse]:
    try:
        records = await service.list_members(current_user, workspace_id)
    except Exception as error:
        _raise_workspace_error(error)
        raise
    return [_member_response(record) for record in records]


async def add_workspace_member(
    workspace_id: UUID,
    payload: WorkspaceMemberCreateRequest,
    current_user: User,
    service: WorkspaceService,
) -> WorkspaceMemberResponse:
    try:
        record = await service.add_member(
            current_user,
            workspace_id,
            payload,
        )
    except Exception as error:
        _raise_workspace_error(error)
        raise
    return _member_response(record)


async def update_workspace_member(
    workspace_id: UUID,
    member_user_id: UUID,
    payload: WorkspaceMemberUpdateRequest,
    current_user: User,
    service: WorkspaceService,
) -> WorkspaceMemberResponse:
    try:
        record = await service.update_member_role(
            current_user,
            workspace_id,
            member_user_id,
            payload,
        )
    except Exception as error:
        _raise_workspace_error(error)
        raise
    return _member_response(record)


async def remove_workspace_member(
    workspace_id: UUID,
    member_user_id: UUID,
    current_user: User,
    service: WorkspaceService,
) -> None:
    try:
        await service.remove_member(
            current_user,
            workspace_id,
            member_user_id,
        )
    except Exception as error:
        _raise_workspace_error(error)
