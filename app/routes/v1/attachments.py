from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.attachment import execute_attachment_action
from app.dependencies.attachment import AttachmentServiceDependency
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.attachment import (
    AttachmentCreateRequest,
    AttachmentDownloadResponse,
    AttachmentResponse,
    AttachmentUploadResponse,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/attachments",
    tags=["Attachments"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/uploads",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an attachment and presigned upload URL",
)
async def create_attachment_upload(
    workspace_id: UUID,
    payload: AttachmentCreateRequest,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
) -> AttachmentUploadResponse:
    attachment, upload_url, expires_at = await execute_attachment_action(
        lambda: service.create_upload(current_user, workspace_id, payload)
    )
    return AttachmentUploadResponse(
        attachment=AttachmentResponse.model_validate(attachment),
        upload_url=upload_url,
        expires_at=expires_at,
    )


@router.post(
    "/{attachment_id}/complete",
    response_model=AttachmentResponse,
    summary="Finish an upload and queue file processing",
)
async def complete_attachment_upload(
    workspace_id: UUID,
    attachment_id: UUID,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
) -> AttachmentResponse:
    attachment = await execute_attachment_action(
        lambda: service.complete_upload(current_user, workspace_id, attachment_id)
    )
    return AttachmentResponse.model_validate(attachment)


@router.get("", response_model=list[AttachmentResponse], summary="List workspace attachments")
async def list_attachments(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
    decision_id: Annotated[UUID | None, Query()] = None,
    proposal_id: Annotated[UUID | None, Query()] = None,
) -> list[AttachmentResponse]:
    attachments = await execute_attachment_action(
        lambda: service.list_attachments(
            current_user,
            workspace_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
        )
    )
    return [AttachmentResponse.model_validate(item) for item in attachments]


@router.get(
    "/{attachment_id}",
    response_model=AttachmentResponse,
    summary="Get attachment metadata",
)
async def get_attachment(
    workspace_id: UUID,
    attachment_id: UUID,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
) -> AttachmentResponse:
    attachment = await execute_attachment_action(
        lambda: service.get(current_user, workspace_id, attachment_id)
    )
    return AttachmentResponse.model_validate(attachment)


@router.post(
    "/{attachment_id}/download",
    response_model=AttachmentDownloadResponse,
    summary="Create a short-lived attachment download URL",
)
async def create_attachment_download(
    workspace_id: UUID,
    attachment_id: UUID,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
) -> AttachmentDownloadResponse:
    download_url, expires_at = await execute_attachment_action(
        lambda: service.download(current_user, workspace_id, attachment_id)
    )
    return AttachmentDownloadResponse(download_url=download_url, expires_at=expires_at)


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment",
)
async def delete_attachment(
    workspace_id: UUID,
    attachment_id: UUID,
    current_user: CurrentUser,
    service: AttachmentServiceDependency,
) -> None:
    await execute_attachment_action(
        lambda: service.delete(current_user, workspace_id, attachment_id)
    )
