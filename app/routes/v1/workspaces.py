from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.controllers.workspace import (
    add_workspace_member,
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspace_members,
    list_workspaces,
    remove_workspace_member,
    update_workspace,
    update_workspace_member,
)
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_service
from app.models.user import User
from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

CurrentUser = Annotated[User, Depends(get_current_user)]
WorkspaceServiceDependency = Annotated[
    WorkspaceService,
    Depends(get_workspace_service),
]


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create(
    payload: WorkspaceCreateRequest,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> WorkspaceResponse:
    return await create_workspace(payload, current_user, service)


@router.get(
    "",
    response_model=list[WorkspaceResponse],
    summary="List the current user's workspaces",
)
async def list_all(
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> list[WorkspaceResponse]:
    return await list_workspaces(current_user, service)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get a workspace",
)
async def get_one(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> WorkspaceResponse:
    return await get_workspace(workspace_id, current_user, service)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update a workspace",
)
async def update(
    workspace_id: UUID,
    payload: WorkspaceUpdateRequest,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> WorkspaceResponse:
    return await update_workspace(
        workspace_id,
        payload,
        current_user,
        service,
    )


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace",
)
async def delete(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> None:
    await delete_workspace(workspace_id, current_user, service)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    summary="List workspace members",
)
async def list_members(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> list[WorkspaceMemberResponse]:
    return await list_workspace_members(
        workspace_id,
        current_user,
        service,
    )


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a workspace member",
)
async def add_member(
    workspace_id: UUID,
    payload: WorkspaceMemberCreateRequest,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> WorkspaceMemberResponse:
    return await add_workspace_member(
        workspace_id,
        payload,
        current_user,
        service,
    )


@router.patch(
    "/{workspace_id}/members/{member_user_id}",
    response_model=WorkspaceMemberResponse,
    summary="Change a workspace member role",
)
async def update_member(
    workspace_id: UUID,
    member_user_id: UUID,
    payload: WorkspaceMemberUpdateRequest,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> WorkspaceMemberResponse:
    return await update_workspace_member(
        workspace_id,
        member_user_id,
        payload,
        current_user,
        service,
    )


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a workspace member",
)
async def remove_member(
    workspace_id: UUID,
    member_user_id: UUID,
    current_user: CurrentUser,
    service: WorkspaceServiceDependency,
) -> None:
    await remove_workspace_member(
        workspace_id,
        member_user_id,
        current_user,
        service,
    )
