from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.integrations.object_storage import ObjectStorage
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.export_search import DecisionExportRepository, SearchRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.export_search import DecisionExportService, ExportPublisher, SearchService
from app.workers.celery_app import celery_app


class CeleryExportPublisher(ExportPublisher):
    def enqueue(self, export_id: UUID) -> None:
        celery_app.send_task("forkroom.exports.generate", args=[str(export_id)])


def get_decision_export_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DecisionExportService:
    settings = get_settings()
    return DecisionExportService(
        DecisionExportRepository(session),
        DecisionLockRepository(session),
        WorkspaceRepository(session),
        ObjectStorage(settings),
        CeleryExportPublisher(),
        url_expire_minutes=settings.export_url_expire_minutes,
    )


def get_search_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SearchService:
    return SearchService(SearchRepository(session), WorkspaceRepository(session))


DecisionExportServiceDependency = Annotated[
    DecisionExportService, Depends(get_decision_export_service)
]
SearchServiceDependency = Annotated[SearchService, Depends(get_search_service)]
