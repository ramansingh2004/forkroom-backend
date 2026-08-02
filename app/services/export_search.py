import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.exceptions import (
    DecisionExportAccessDeniedError,
    DecisionExportInvalidStateError,
    DecisionExportNotFoundError,
    DecisionLockNotFoundError,
    SearchAccessDeniedError,
    WorkspaceNotFoundError,
)
from app.integrations.object_storage import ObjectStorage
from app.integrations.pdf_export import DecisionPdfRenderer
from app.models.export_search import DecisionExport, ExportStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.export_search import (
    DecisionExportRepository,
    SearchRepository,
    SearchResultRecord,
)
from app.repositories.workspace import WorkspaceRepository


class ExportPublisher(Protocol):
    def enqueue(self, export_id: UUID) -> None: ...


class SearchPublisher(Protocol):
    def enqueue(self, decision_id: UUID) -> None: ...


class DecisionExportService:
    def __init__(
        self,
        exports: DecisionExportRepository,
        locks: DecisionLockRepository,
        workspaces: WorkspaceRepository,
        storage: ObjectStorage,
        publisher: ExportPublisher,
        *,
        url_expire_minutes: int,
    ) -> None:
        self._exports = exports
        self._locks = locks
        self._workspaces = workspaces
        self._storage = storage
        self._publisher = publisher
        self._url_expire_minutes = url_expire_minutes

    async def request(
        self, current_user: User, workspace_id: UUID, decision_id: UUID
    ) -> DecisionExport:
        membership = await self._membership(current_user.id, workspace_id)
        if membership.role is WorkspaceRole.VIEWER:
            raise DecisionExportAccessDeniedError
        decision_lock = await self._locks.get_for_decision(decision_id)
        decision_snapshot = (
            self._mapping(decision_lock.snapshot.get("decision"))
            if decision_lock is not None
            else {}
        )
        if decision_lock is None or str(decision_snapshot.get("workspace_id")) != str(workspace_id):
            raise DecisionLockNotFoundError
        existing = await self._exports.get_for_lock(decision_lock.id)
        if existing is not None:
            if existing.status is ExportStatus.FAILED:
                existing = await self._exports.reset_failed(existing)
                self._publisher.enqueue(existing.id)
            return existing

        title = str(decision_snapshot.get("title", "decision"))
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "decision"
        filename = f"{slug}-{decision_lock.document_hash[:12]}.pdf"
        export = DecisionExport(
            workspace_id=workspace_id,
            decision_id=decision_id,
            decision_lock_id=decision_lock.id,
            requested_by_id=current_user.id,
            document_hash=decision_lock.document_hash,
            object_key=(
                f"exports/{workspace_id}/{decision_id}/{decision_lock.document_hash}/{filename}"
            ),
            filename=filename,
        )
        created = await self._exports.create(export)
        self._publisher.enqueue(created.id)
        return created

    async def get(
        self, current_user: User, workspace_id: UUID, decision_id: UUID
    ) -> DecisionExport:
        await self._membership(current_user.id, workspace_id)
        export = await self._exports.get_for_decision(decision_id)
        if export is None or export.workspace_id != workspace_id:
            raise DecisionExportNotFoundError
        return export

    async def download(
        self, current_user: User, workspace_id: UUID, decision_id: UUID
    ) -> tuple[str, datetime]:
        export = await self.get(current_user, workspace_id, decision_id)
        if export.status is not ExportStatus.AVAILABLE:
            raise DecisionExportInvalidStateError
        expires = timedelta(minutes=self._url_expire_minutes)
        url = await self._storage.presigned_download(export.object_key, export.filename, expires)
        return url, datetime.now(UTC) + expires

    async def _membership(self, user_id: UUID, workspace_id: UUID) -> WorkspaceMember:
        workspace = await self._workspaces.get_by_id(workspace_id)
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError
        return membership

    @staticmethod
    def _mapping(value: object) -> dict[str, object]:
        return value if isinstance(value, dict) else {}


class DecisionExportProcessingService:
    def __init__(
        self,
        exports: DecisionExportRepository,
        locks: DecisionLockRepository,
        storage: ObjectStorage,
        renderer: DecisionPdfRenderer,
    ) -> None:
        self._exports = exports
        self._locks = locks
        self._storage = storage
        self._renderer = renderer

    async def process(self, export_id: UUID) -> str:
        export = await self._exports.claim(export_id, datetime.now(UTC))
        if export is None:
            return "ignored"
        decision_lock = await self._locks.get_for_decision(export.decision_id)
        if decision_lock is None or decision_lock.id != export.decision_lock_id:
            raise DecisionLockNotFoundError
        computed_hash = self._hash_snapshot(decision_lock.snapshot)
        if computed_hash != export.document_hash or computed_hash != decision_lock.document_hash:
            raise DecisionExportInvalidStateError
        pdf = self._renderer.render(
            decision_lock.snapshot,
            document_hash=decision_lock.document_hash,
            snapshot_version=decision_lock.snapshot_version,
            locked_at=decision_lock.locked_at.isoformat(),
        )
        await self._storage.put_bytes(export.object_key, pdf, "application/pdf")
        await self._exports.mark_available(
            export, size_bytes=len(pdf), completed_at=datetime.now(UTC)
        )
        return "available"

    @staticmethod
    def _hash_snapshot(snapshot: dict[str, object]) -> str:
        canonical = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        return hashlib.sha256(canonical).hexdigest()


class SearchIndexService:
    def __init__(self, repository: SearchRepository) -> None:
        self._repository = repository

    async def stale(self) -> list[UUID]:
        return await self._repository.list_stale_decision_ids()

    async def index(self, decision_id: UUID) -> str:
        source = await self._repository.get_index_source(decision_id)
        if source is None:
            return "missing"
        decision, proposals, decision_lock = source
        sections = [decision.summary or ""]
        for proposal in proposals:
            sections.extend([proposal.title, proposal.summary or "", proposal.content or ""])
        if decision_lock is not None:
            sections.append(json.dumps(decision_lock.snapshot, ensure_ascii=False))
        body = "\n".join(section for section in sections if section).strip()
        await self._repository.upsert(
            decision=decision,
            body=body,
            indexed_at=datetime.now(UTC),
        )
        return "indexed"


class SearchService:
    def __init__(self, repository: SearchRepository, workspaces: WorkspaceRepository) -> None:
        self._repository = repository
        self._workspaces = workspaces

    async def search(
        self,
        current_user: User,
        workspace_id: UUID,
        query: str,
        *,
        status: str | None,
        category: str | None,
        limit: int,
        offset: int,
    ) -> list[SearchResultRecord]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        membership = await self._workspaces.get_membership(workspace_id, current_user.id)
        if workspace is None:
            raise WorkspaceNotFoundError
        if membership is None:
            raise SearchAccessDeniedError
        return await self._repository.search(
            workspace_id,
            query,
            status=status,
            category=category,
            limit=limit,
            offset=offset,
        )
