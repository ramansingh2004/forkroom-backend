from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    DecisionExportAccessDeniedError,
    DecisionExportInvalidStateError,
    SearchAccessDeniedError,
)
from app.models.decision import Decision, DecisionCategory, DecisionLock, DecisionStatus
from app.models.export_search import DecisionExport, ExportStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.services.decision_lock import DecisionLockService
from app.services.export_search import (
    DecisionExportProcessingService,
    DecisionExportService,
    SearchIndexService,
    SearchService,
)


def export_context(role: WorkspaceRole = WorkspaceRole.MEMBER):
    exports = AsyncMock()
    locks = AsyncMock()
    workspaces = AsyncMock()
    storage = AsyncMock()
    publisher = Mock()
    user = User(id=uuid4(), email="raman@example.com", password_hash="hash", display_name="Raman")
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=user.id)
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = WorkspaceMember(
        id=uuid4(), workspace_id=workspace.id, user_id=user.id, role=role
    )
    decision_id = uuid4()
    snapshot: dict[str, object] = {
        "decision": {
            "id": str(decision_id),
            "workspace_id": str(workspace.id),
            "title": "Choose the API framework",
            "category": "architecture",
            "summary": "Select a maintainable backend.",
            "review_at": None,
        },
        "approved_proposal": {"title": "Use FastAPI", "content": "Typed async APIs"},
        "voting_result": {"tallies": []},
        "dissent": {"objections_to_approved_proposal": [], "alternative_proposals": []},
    }
    lock = DecisionLock(
        id=uuid4(),
        decision_id=decision_id,
        voting_session_id=uuid4(),
        winning_proposal_id=uuid4(),
        locked_by_id=user.id,
        snapshot_version=1,
        snapshot=snapshot,
        document_hash=DecisionLockService.hash_snapshot(snapshot),
        locked_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    locks.get_for_decision.return_value = lock
    service = DecisionExportService(
        exports,
        locks,
        workspaces,
        storage,
        publisher,
        url_expire_minutes=15,
    )
    return service, exports, storage, publisher, user, workspace, lock


async def test_member_requests_content_addressed_export_once() -> None:
    service, exports, _, publisher, user, workspace, lock = export_context()
    exports.get_for_lock.return_value = None
    exports.create.side_effect = lambda item: item

    result = await service.request(user, workspace.id, lock.decision_id)

    assert result.document_hash == lock.document_hash
    assert lock.document_hash in result.object_key
    assert result.filename.endswith(".pdf")
    publisher.enqueue.assert_called_once_with(result.id)


async def test_existing_export_is_idempotently_reused() -> None:
    service, exports, _, publisher, user, workspace, lock = export_context()
    existing = DecisionExport(
        id=uuid4(),
        workspace_id=workspace.id,
        decision_id=lock.decision_id,
        decision_lock_id=lock.id,
        requested_by_id=user.id,
        document_hash=lock.document_hash,
        object_key="exports/key.pdf",
        filename="key.pdf",
        status=ExportStatus.PROCESSING,
        attempt_count=1,
    )
    exports.get_for_lock.return_value = existing

    assert await service.request(user, workspace.id, lock.decision_id) is existing
    publisher.enqueue.assert_not_called()


async def test_viewer_cannot_request_export() -> None:
    service, _, _, _, user, workspace, lock = export_context(WorkspaceRole.VIEWER)
    with pytest.raises(DecisionExportAccessDeniedError):
        await service.request(user, workspace.id, lock.decision_id)


async def test_only_available_export_can_be_downloaded() -> None:
    service, exports, storage, _, user, workspace, lock = export_context()
    export = DecisionExport(
        id=uuid4(),
        workspace_id=workspace.id,
        decision_id=lock.decision_id,
        decision_lock_id=lock.id,
        requested_by_id=user.id,
        document_hash=lock.document_hash,
        object_key="exports/key.pdf",
        filename="key.pdf",
        status=ExportStatus.AVAILABLE,
        attempt_count=1,
        size_bytes=100,
        completed_at=datetime.now(UTC),
    )
    exports.get_for_decision.return_value = export
    storage.presigned_download.return_value = "http://localhost:9000/export"
    url, _ = await service.download(user, workspace.id, lock.decision_id)
    assert url.endswith("/export")

    export.status = ExportStatus.PENDING
    with pytest.raises(DecisionExportInvalidStateError):
        await service.download(user, workspace.id, lock.decision_id)


async def test_processing_verifies_hash_uploads_pdf_and_marks_available() -> None:
    _, exports, storage, _, user, workspace, lock = export_context()
    export = DecisionExport(
        id=uuid4(),
        workspace_id=workspace.id,
        decision_id=lock.decision_id,
        decision_lock_id=lock.id,
        requested_by_id=user.id,
        document_hash=lock.document_hash,
        object_key="exports/key.pdf",
        filename="key.pdf",
        status=ExportStatus.PROCESSING,
        attempt_count=1,
    )
    exports.claim.return_value = export
    locks = AsyncMock()
    locks.get_for_decision.return_value = lock
    renderer = Mock()
    renderer.render.return_value = b"%PDF-test"
    service = DecisionExportProcessingService(exports, locks, storage, renderer)

    assert await service.process(export.id) == "available"
    storage.put_bytes.assert_awaited_once_with(export.object_key, b"%PDF-test", "application/pdf")
    exports.mark_available.assert_awaited_once()


async def test_processing_rejects_tampered_snapshot() -> None:
    _, exports, storage, _, user, workspace, lock = export_context()
    export = DecisionExport(
        id=uuid4(),
        workspace_id=workspace.id,
        decision_id=lock.decision_id,
        decision_lock_id=lock.id,
        requested_by_id=user.id,
        document_hash="0" * 64,
        object_key="exports/key.pdf",
        filename="key.pdf",
        status=ExportStatus.PROCESSING,
        attempt_count=1,
    )
    exports.claim.return_value = export
    locks = AsyncMock()
    locks.get_for_decision.return_value = lock
    service = DecisionExportProcessingService(exports, locks, storage, Mock())
    with pytest.raises(DecisionExportInvalidStateError):
        await service.process(export.id)
    storage.put_bytes.assert_not_awaited()


async def test_search_index_combines_decision_proposals_and_lock_snapshot() -> None:
    repository = AsyncMock()
    decision = Decision(
        id=uuid4(),
        workspace_id=uuid4(),
        created_by_id=uuid4(),
        title="Queue choice",
        summary="Choose transport",
        category=DecisionCategory.ARCHITECTURE,
        status=DecisionStatus.LOCKED,
    )
    proposal = Proposal(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        title="Use RabbitMQ",
        summary="Reliable jobs",
        content="Dead-letter queues",
        status=ProposalStatus.SUBMITTED,
    )
    lock = Mock(snapshot={"approved_proposal": {"title": "Use RabbitMQ"}})
    repository.get_index_source.return_value = (decision, [proposal], lock)

    assert await SearchIndexService(repository).index(decision.id) == "indexed"
    body = repository.upsert.await_args.kwargs["body"]
    assert "Dead-letter queues" in body
    assert "approved_proposal" in body


async def test_nonmember_cannot_search_workspace() -> None:
    repository = AsyncMock()
    workspaces = AsyncMock()
    workspace_id = uuid4()
    workspaces.get_by_id.return_value = Workspace(id=workspace_id, name="Guild", owner_id=uuid4())
    workspaces.get_membership.return_value = None
    user = User(id=uuid4(), email="r@example.com", password_hash="hash", display_name="R")

    with pytest.raises(SearchAccessDeniedError):
        await SearchService(repository, workspaces).search(
            user, workspace_id, "rabbitmq", status=None, category=None, limit=20, offset=0
        )
