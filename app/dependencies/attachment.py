from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.integrations.object_storage import ObjectStorage
from app.repositories.attachment import AttachmentRepository
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.attachment import AttachmentPublisher, AttachmentService
from app.workers.celery_app import celery_app


class CeleryAttachmentPublisher(AttachmentPublisher):
    def enqueue_processing(self, attachment_id: UUID) -> None:
        celery_app.send_task("forkroom.attachments.process", args=[str(attachment_id)])


def get_attachment_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AttachmentService:
    settings = get_settings()
    return AttachmentService(
        AttachmentRepository(session),
        WorkspaceRepository(session),
        DecisionRepository(session),
        ProposalRepository(session),
        ObjectStorage(settings),
        CeleryAttachmentPublisher(),
        max_bytes=settings.attachment_max_bytes,
        url_expire_minutes=settings.attachment_url_expire_minutes,
    )


AttachmentServiceDependency = Annotated[AttachmentService, Depends(get_attachment_service)]
