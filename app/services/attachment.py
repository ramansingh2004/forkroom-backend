from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from app.core.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentInvalidStateError,
    AttachmentInvalidTargetError,
    AttachmentNotFoundError,
    AttachmentTooLargeError,
    AttachmentValidationError,
    WorkspaceNotFoundError,
)
from app.integrations.object_storage import ObjectStorage
from app.models.attachment import Attachment, AttachmentStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.permissions.attachment import can_delete_attachment, can_upload_attachment
from app.repositories.attachment import AttachmentRepository
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.attachment import AttachmentCreateRequest


class AttachmentPublisher(Protocol):
    def enqueue_processing(self, attachment_id: UUID) -> None: ...


class AttachmentService:
    def __init__(
        self,
        attachment_repository: AttachmentRepository,
        workspace_repository: WorkspaceRepository,
        decision_repository: DecisionRepository,
        proposal_repository: ProposalRepository,
        storage: ObjectStorage,
        publisher: AttachmentPublisher,
        *,
        max_bytes: int,
        url_expire_minutes: int,
    ) -> None:
        self._attachments = attachment_repository
        self._workspaces = workspace_repository
        self._decisions = decision_repository
        self._proposals = proposal_repository
        self._storage = storage
        self._publisher = publisher
        self._max_bytes = max_bytes
        self._url_expire_minutes = url_expire_minutes

    async def create_upload(
        self,
        current_user: User,
        workspace_id: UUID,
        payload: AttachmentCreateRequest,
    ) -> tuple[Attachment, str, datetime]:
        membership = await self._membership(current_user.id, workspace_id)
        if not can_upload_attachment(membership.role):
            raise AttachmentAccessDeniedError
        if payload.size_bytes > self._max_bytes:
            raise AttachmentTooLargeError
        await self._validate_target(workspace_id, payload.decision_id, payload.proposal_id)

        attachment_id = uuid4()
        object_key = f"workspaces/{workspace_id}/attachments/{attachment_id}/{payload.filename}"
        expires_at = datetime.now(UTC) + timedelta(minutes=self._url_expire_minutes)
        upload_url = await self._storage.presigned_upload(
            object_key,
            timedelta(minutes=self._url_expire_minutes),
        )
        attachment = await self._attachments.create(
            Attachment(
                id=attachment_id,
                workspace_id=workspace_id,
                decision_id=payload.decision_id,
                proposal_id=payload.proposal_id,
                uploaded_by_id=current_user.id,
                object_key=object_key,
                filename=payload.filename,
                media_type=payload.media_type,
                size_bytes=payload.size_bytes,
                status=AttachmentStatus.PENDING,
                processing_attempts=0,
            )
        )
        return attachment, upload_url, expires_at

    async def complete_upload(
        self,
        current_user: User,
        workspace_id: UUID,
        attachment_id: UUID,
    ) -> Attachment:
        membership = await self._membership(current_user.id, workspace_id)
        attachment = await self._require_attachment(workspace_id, attachment_id)
        if not can_delete_attachment(
            membership.role,
            uploaded_by_id=attachment.uploaded_by_id,
            user_id=current_user.id,
        ):
            raise AttachmentAccessDeniedError
        if attachment.status is not AttachmentStatus.PENDING:
            raise AttachmentInvalidStateError
        attachment = await self._attachments.update(
            attachment,
            values={"status": AttachmentStatus.PROCESSING, "processing_error": None},
        )
        self._publisher.enqueue_processing(attachment.id)
        return attachment

    async def list_attachments(
        self,
        current_user: User,
        workspace_id: UUID,
        *,
        decision_id: UUID | None,
        proposal_id: UUID | None,
    ) -> list[Attachment]:
        await self._membership(current_user.id, workspace_id)
        if proposal_id is not None and decision_id is None:
            raise AttachmentInvalidTargetError
        return await self._attachments.list_for_workspace(
            workspace_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
        )

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
        attachment_id: UUID,
    ) -> Attachment:
        await self._membership(current_user.id, workspace_id)
        return await self._require_attachment(workspace_id, attachment_id)

    async def download(
        self,
        current_user: User,
        workspace_id: UUID,
        attachment_id: UUID,
    ) -> tuple[str, datetime]:
        attachment = await self.get(current_user, workspace_id, attachment_id)
        if attachment.status is not AttachmentStatus.AVAILABLE:
            raise AttachmentInvalidStateError
        expires_at = datetime.now(UTC) + timedelta(minutes=self._url_expire_minutes)
        url = await self._storage.presigned_download(
            attachment.object_key,
            attachment.filename,
            timedelta(minutes=self._url_expire_minutes),
        )
        return url, expires_at

    async def delete(
        self,
        current_user: User,
        workspace_id: UUID,
        attachment_id: UUID,
    ) -> None:
        membership = await self._membership(current_user.id, workspace_id)
        attachment = await self._require_attachment(workspace_id, attachment_id)
        if not can_delete_attachment(
            membership.role,
            uploaded_by_id=attachment.uploaded_by_id,
            user_id=current_user.id,
        ):
            raise AttachmentAccessDeniedError
        await self._storage.remove(attachment.object_key)
        await self._attachments.update(
            attachment,
            values={"status": AttachmentStatus.DELETED, "deleted_at": datetime.now(UTC)},
        )

    async def _membership(self, user_id: UUID, workspace_id: UUID) -> WorkspaceMember:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        return membership

    async def _validate_target(
        self,
        workspace_id: UUID,
        decision_id: UUID | None,
        proposal_id: UUID | None,
    ) -> None:
        if proposal_id is not None and decision_id is None:
            raise AttachmentInvalidTargetError
        if decision_id is None:
            return
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise AttachmentInvalidTargetError
        if proposal_id is not None:
            proposal = await self._proposals.get_for_decision(decision_id, proposal_id)
            if proposal is None:
                raise AttachmentInvalidTargetError

    async def _require_attachment(
        self,
        workspace_id: UUID,
        attachment_id: UUID,
    ) -> Attachment:
        attachment = await self._attachments.get(workspace_id, attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError
        return attachment


class AttachmentProcessingService:
    def __init__(
        self,
        repository: AttachmentRepository,
        storage: ObjectStorage,
        *,
        max_bytes: int,
    ) -> None:
        self._attachments = repository
        self._storage = storage
        self._max_bytes = max_bytes

    async def process(self, attachment_id: UUID) -> str:
        attachment = await self._attachments.claim_processing(attachment_id)
        if attachment is None:
            return "ignored"
        info = await self._storage.stat(attachment.object_key)
        if info.size != attachment.size_bytes:
            raise AttachmentValidationError("Uploaded object size does not match the declared size")
        if info.size > self._max_bytes:
            raise AttachmentValidationError("Uploaded object exceeds the configured size limit")
        sha256 = await self._storage.sha256(attachment.object_key)
        await self._attachments.mark_available(
            attachment,
            sha256=sha256,
            processed_at=datetime.now(UTC),
        )
        return "available"
