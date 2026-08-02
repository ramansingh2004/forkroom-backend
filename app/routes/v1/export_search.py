from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.export_search import execute_export_search_action
from app.dependencies.auth import get_current_user
from app.dependencies.export_search import (
    DecisionExportServiceDependency,
    SearchServiceDependency,
)
from app.models.decision import DecisionCategory, DecisionStatus
from app.models.user import User
from app.schemas.export_search import (
    DecisionExportDownloadResponse,
    DecisionExportResponse,
    SearchResponse,
    SearchResultResponse,
)

router = APIRouter(tags=["Exports and Search"])
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/workspaces/{workspace_id}/decisions/{decision_id}/exports",
    response_model=DecisionExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request an immutable decision PDF export",
)
async def request_decision_export(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionExportServiceDependency,
) -> DecisionExportResponse:
    export = await execute_export_search_action(
        lambda: service.request(current_user, workspace_id, decision_id)
    )
    return DecisionExportResponse.model_validate(export)


@router.get(
    "/workspaces/{workspace_id}/decisions/{decision_id}/exports",
    response_model=DecisionExportResponse,
    summary="Get decision PDF export status",
)
async def get_decision_export(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionExportServiceDependency,
) -> DecisionExportResponse:
    export = await execute_export_search_action(
        lambda: service.get(current_user, workspace_id, decision_id)
    )
    return DecisionExportResponse.model_validate(export)


@router.post(
    "/workspaces/{workspace_id}/decisions/{decision_id}/exports/download",
    response_model=DecisionExportDownloadResponse,
    summary="Create a short-lived decision PDF download URL",
)
async def download_decision_export(
    workspace_id: UUID,
    decision_id: UUID,
    current_user: CurrentUser,
    service: DecisionExportServiceDependency,
) -> DecisionExportDownloadResponse:
    url, expires_at = await execute_export_search_action(
        lambda: service.download(current_user, workspace_id, decision_id)
    )
    return DecisionExportDownloadResponse(download_url=url, expires_at=expires_at)


@router.get(
    "/workspaces/{workspace_id}/search",
    response_model=SearchResponse,
    summary="Search indexed workspace decisions and proposals",
)
async def search_workspace(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: SearchServiceDependency,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    decision_status: Annotated[DecisionStatus | None, Query(alias="status")] = None,
    category: Annotated[DecisionCategory | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResponse:
    results = await execute_export_search_action(
        lambda: service.search(
            current_user,
            workspace_id,
            q,
            status=decision_status.value if decision_status else None,
            category=category.value if category else None,
            limit=limit,
            offset=offset,
        )
    )
    return SearchResponse(
        query=q,
        results=[
            SearchResultResponse(
                decision_id=result.decision_id,
                title=result.title,
                status=result.status,
                category=result.category,
                headline=result.headline,
                rank=result.rank,
                indexed_at=result.indexed_at,
            )
            for result in results
        ],
        limit=limit,
        offset=offset,
    )
