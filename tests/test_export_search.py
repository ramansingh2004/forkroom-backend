from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core.exceptions import DecisionExportInvalidStateError
from app.dependencies.auth import get_current_user
from app.dependencies.export_search import get_decision_export_service, get_search_service
from app.main import app
from app.models.export_search import DecisionExport, ExportStatus
from app.models.user import User
from app.repositories.export_search import SearchResultRecord
from app.services.export_search import DecisionExportService, SearchService


@pytest.fixture
def export_search_user() -> User:
    return User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture
def export_service(export_search_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=DecisionExportService)
    app.dependency_overrides[get_current_user] = lambda: export_search_user
    app.dependency_overrides[get_decision_export_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_decision_export_service, None)


@pytest.fixture
def search_service(export_search_user: User) -> Iterator[AsyncMock]:
    service = AsyncMock(spec=SearchService)
    app.dependency_overrides[get_current_user] = lambda: export_search_user
    app.dependency_overrides[get_search_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_search_service, None)


def make_export(user: User, workspace_id: UUID, decision_id: UUID) -> DecisionExport:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    return DecisionExport(
        id=uuid4(),
        workspace_id=workspace_id,
        decision_id=decision_id,
        decision_lock_id=uuid4(),
        requested_by_id=user.id,
        document_hash="a" * 64,
        object_key="exports/result.pdf",
        filename="result.pdf",
        status=ExportStatus.PENDING,
        attempt_count=0,
        created_at=now,
    )


async def test_request_export_returns_accepted(
    client: AsyncClient,
    export_service: AsyncMock,
    export_search_user: User,
) -> None:
    workspace_id, decision_id = uuid4(), uuid4()
    export_service.request.return_value = make_export(export_search_user, workspace_id, decision_id)
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/decisions/{decision_id}/exports"
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"


async def test_export_download_conflict_is_mapped(
    client: AsyncClient, export_service: AsyncMock
) -> None:
    export_service.download.side_effect = DecisionExportInvalidStateError
    response = await client.post(
        f"/api/v1/workspaces/{uuid4()}/decisions/{uuid4()}/exports/download"
    )
    assert response.status_code == 409


async def test_search_returns_ranked_highlights(
    client: AsyncClient, search_service: AsyncMock
) -> None:
    workspace_id, decision_id = uuid4(), uuid4()
    search_service.search.return_value = [
        SearchResultRecord(
            decision_id=decision_id,
            title="Queue choice",
            status="locked",
            category="architecture",
            headline="Use <mark>RabbitMQ</mark> for reliable jobs",
            rank=0.82,
            indexed_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    ]
    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search?q=rabbitmq&status=locked"
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["decision_id"] == str(decision_id)
    assert "<mark>" in response.json()["results"][0]["headline"]


async def test_search_rejects_too_short_query(
    client: AsyncClient, search_service: AsyncMock
) -> None:
    response = await client.get(f"/api/v1/workspaces/{uuid4()}/search?q=x")
    assert response.status_code == 422
    search_service.search.assert_not_awaited()
