from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentInvalidStateError,
    AttachmentInvalidTargetError,
    AttachmentTooLargeError,
)
from app.integrations.object_storage import StoredObjectInfo
from app.models.attachment import Attachment, AttachmentStatus
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.schemas.attachment import AttachmentCreateRequest
from app.services.attachment import AttachmentProcessingService, AttachmentService


def make_context(
    role: WorkspaceRole = WorkspaceRole.MEMBER,
) -> tuple[AttachmentService, AsyncMock, AsyncMock, Mock, AsyncMock, User, Workspace]:
    attachments = AsyncMock()
    workspaces = AsyncMock()
    decisions = AsyncMock()
    proposals = AsyncMock()
    storage = AsyncMock()
    publisher = Mock()
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
    )
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=user.id)
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = WorkspaceMember(
        id=uuid4(), workspace_id=workspace.id, user_id=user.id, role=role
    )
    service = AttachmentService(
        attachments,
        workspaces,
        decisions,
        proposals,
        storage,
        publisher,
        max_bytes=1024,
        url_expire_minutes=15,
    )
    return service, attachments, storage, publisher, decisions, user, workspace


def persisted(attachment: Attachment) -> Attachment:
    attachments_dates = {"created_at", "updated_at"}
    for field in attachments_dates:
        if getattr(attachment, field, None) is None:
            setattr(attachment, field, None)
    return attachment


async def test_member_creates_workspace_attachment() -> None:
    service, attachments, storage, _, _, user, workspace = make_context()
    attachments.create.side_effect = lambda item: item
    storage.presigned_upload.return_value = "http://localhost:9000/upload"
    payload = AttachmentCreateRequest(
        filename="../architecture.pdf",
        media_type="application/pdf",
        size_bytes=512,
    )

    attachment, url, _ = await service.create_upload(user, workspace.id, payload)

    assert attachment.filename == "architecture.pdf"
    assert attachment.status is AttachmentStatus.PENDING
    assert url == "http://localhost:9000/upload"
    storage.presigned_upload.assert_awaited_once()
    assert isinstance(storage.presigned_upload.await_args.args[1], timedelta)


async def test_viewer_cannot_upload() -> None:
    service, _, _, _, _, user, workspace = make_context(WorkspaceRole.VIEWER)
    with pytest.raises(AttachmentAccessDeniedError):
        await service.create_upload(
            user,
            workspace.id,
            AttachmentCreateRequest(
                filename="evidence.pdf",
                media_type="application/pdf",
                size_bytes=512,
            ),
        )


async def test_oversized_upload_is_rejected_before_storage() -> None:
    service, _, storage, _, _, user, workspace = make_context()
    with pytest.raises(AttachmentTooLargeError):
        await service.create_upload(
            user,
            workspace.id,
            AttachmentCreateRequest(
                filename="large.zip",
                media_type="application/zip",
                size_bytes=1025,
            ),
        )
    storage.presigned_upload.assert_not_awaited()


async def test_proposal_target_must_belong_to_decision() -> None:
    service, _, _, _, decisions, user, workspace = make_context()
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose storage",
        category=DecisionCategory.ARCHITECTURE,
        status=DecisionStatus.ACTIVE,
    )
    decisions.get_for_workspace.return_value = decision
    service._proposals.get_for_decision.return_value = None  # type: ignore[attr-defined]
    with pytest.raises(AttachmentInvalidTargetError):
        await service.create_upload(
            user,
            workspace.id,
            AttachmentCreateRequest(
                filename="evidence.pdf",
                media_type="application/pdf",
                size_bytes=512,
                decision_id=decision.id,
                proposal_id=uuid4(),
            ),
        )


async def test_complete_transitions_and_publishes() -> None:
    service, attachments, _, publisher, _, user, workspace = make_context()
    attachment = Attachment(
        id=uuid4(),
        workspace_id=workspace.id,
        uploaded_by_id=user.id,
        object_key="key",
        filename="file.pdf",
        media_type="application/pdf",
        size_bytes=10,
        status=AttachmentStatus.PENDING,
        processing_attempts=0,
    )
    attachments.get.return_value = attachment
    attachments.update.side_effect = lambda item, **_: item

    result = await service.complete_upload(user, workspace.id, attachment.id)

    assert result is attachment
    attachments.update.assert_awaited_once()
    publisher.enqueue_processing.assert_called_once_with(attachment.id)


async def test_available_attachment_gets_download_url() -> None:
    service, attachments, storage, _, _, user, workspace = make_context()
    attachment = Attachment(
        id=uuid4(),
        workspace_id=workspace.id,
        uploaded_by_id=user.id,
        object_key="key",
        filename="file.pdf",
        media_type="application/pdf",
        size_bytes=10,
        status=AttachmentStatus.AVAILABLE,
        processing_attempts=1,
    )
    attachments.get.return_value = attachment
    storage.presigned_download.return_value = "http://localhost:9000/download"
    url, _ = await service.download(user, workspace.id, attachment.id)
    assert url.endswith("/download")


async def test_pending_attachment_cannot_be_downloaded() -> None:
    service, attachments, _, _, _, user, workspace = make_context()
    attachment = Attachment(
        id=uuid4(),
        workspace_id=workspace.id,
        uploaded_by_id=user.id,
        object_key="key",
        filename="file.pdf",
        media_type="application/pdf",
        size_bytes=10,
        status=AttachmentStatus.PENDING,
        processing_attempts=0,
    )
    attachments.get.return_value = attachment
    with pytest.raises(AttachmentInvalidStateError):
        await service.download(user, workspace.id, attachment.id)


async def test_processing_hashes_and_marks_attachment_available() -> None:
    attachment_id = uuid4()
    attachment = Attachment(
        id=attachment_id,
        workspace_id=uuid4(),
        uploaded_by_id=uuid4(),
        object_key="key",
        filename="file.pdf",
        media_type="application/pdf",
        size_bytes=10,
        status=AttachmentStatus.PROCESSING,
        processing_attempts=0,
    )
    repository = AsyncMock()
    repository.claim_processing.return_value = attachment
    storage = AsyncMock()
    storage.stat.return_value = StoredObjectInfo(size=10, content_type="application/pdf")
    storage.sha256.return_value = "a" * 64
    service = AttachmentProcessingService(repository, storage, max_bytes=1024)

    assert await service.process(attachment_id) == "available"
    repository.mark_available.assert_awaited_once()


async def test_processing_rejects_size_mismatch() -> None:
    attachment = Attachment(
        id=uuid4(),
        workspace_id=uuid4(),
        uploaded_by_id=uuid4(),
        object_key="key",
        filename="file.pdf",
        media_type="application/pdf",
        size_bytes=10,
        status=AttachmentStatus.PROCESSING,
        processing_attempts=0,
    )
    repository = AsyncMock()
    repository.claim_processing.return_value = attachment
    storage = AsyncMock()
    storage.stat.return_value = StoredObjectInfo(size=11, content_type="application/pdf")
    service = AttachmentProcessingService(repository, storage, max_bytes=1024)

    with pytest.raises(ValueError, match="declared size"):
        await service.process(attachment.id)
