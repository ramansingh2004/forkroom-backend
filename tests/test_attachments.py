from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentInvalidStateError,
    AttachmentInvalidTargetError,
    AttachmentNotFoundError,
    AttachmentTooLargeError,
)
from app.dependencies.attachment import get_attachment_service
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.attachment import Attachment, AttachmentStatus
from app.models.user import User
from app.services.attachment import AttachmentService


@pytest.fixture
def attachment_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture
def attachment_service(attachment_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=AttachmentService)
    app.dependency_overrides[get_current_user] = lambda: attachment_user
    app.dependency_overrides[get_attachment_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_attachment_service, None)


def make_attachment(user: User, workspace_id: object) -> Attachment:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    return Attachment(
        id=uuid4(),
        workspace_id=workspace_id,
        uploaded_by_id=user.id,
        object_key=f"workspaces/{workspace_id}/attachments/file.pdf",
        filename="architecture.pdf",
        media_type="application/pdf",
        size_bytes=2048,
        status=AttachmentStatus.PENDING,
        processing_attempts=0,
        created_at=now,
        updated_at=now,
    )


async def test_create_upload_returns_presigned_url(
    client: AsyncClient,
    attachment_user: User,
    attachment_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    attachment = make_attachment(attachment_user, workspace_id)
    expires_at = datetime(2026, 8, 1, 0, 15, tzinfo=UTC)
    attachment_service.create_upload.return_value = (
        attachment,
        "http://localhost:9000/upload",
        expires_at,
    )

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/attachments/uploads",
        json={
            "filename": "architecture.pdf",
            "media_type": "application/pdf",
            "size_bytes": 2048,
        },
    )

    assert response.status_code == 201
    assert response.json()["upload_url"] == "http://localhost:9000/upload"
    assert response.json()["attachment"]["status"] == "pending"


async def test_complete_upload_queues_processing(
    client: AsyncClient,
    attachment_user: User,
    attachment_service: AsyncMock,
) -> None:
    workspace_id = uuid4()
    attachment = make_attachment(attachment_user, workspace_id)
    attachment.status = AttachmentStatus.PROCESSING
    attachment_service.complete_upload.return_value = attachment

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/attachments/{attachment.id}/complete"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processing"


async def test_download_returns_short_lived_url(
    client: AsyncClient,
    attachment_service: AsyncMock,
) -> None:
    expires_at = datetime(2026, 8, 1, 0, 15, tzinfo=UTC)
    attachment_service.download.return_value = (
        "http://localhost:9000/download",
        expires_at,
    )
    response = await client.post(f"/api/v1/workspaces/{uuid4()}/attachments/{uuid4()}/download")
    assert response.status_code == 200
    assert response.json()["download_url"] == "http://localhost:9000/download"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AttachmentNotFoundError(), 404),
        (AttachmentAccessDeniedError(), 403),
        (AttachmentTooLargeError(), 413),
        (AttachmentInvalidTargetError(), 422),
        (AttachmentInvalidStateError(), 409),
    ],
)
async def test_attachment_errors_are_mapped(
    client: AsyncClient,
    attachment_service: AsyncMock,
    error: Exception,
    expected_status: int,
) -> None:
    attachment_service.get.side_effect = error
    response = await client.get(f"/api/v1/workspaces/{uuid4()}/attachments/{uuid4()}")
    assert response.status_code == expected_status
