from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.controllers.collaboration import execute_collaboration_action
from app.dependencies.auth import get_current_user
from app.dependencies.collaboration import get_collaboration_service
from app.models.user import User
from app.schemas.collaboration import CollaborationTokenResponse
from app.services.collaboration import CollaborationService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/decisions/{decision_id}/proposals/{proposal_id}",
    tags=["Collaboration"],
)

CurrentUser = Annotated[User, Depends(get_current_user)]
CollaborationServiceDependency = Annotated[CollaborationService, Depends(get_collaboration_service)]


@router.post(
    "/collaboration-token",
    response_model=CollaborationTokenResponse,
    summary="Issue a short-lived document-scoped collaboration token",
)
async def issue_collaboration_token(
    workspace_id: UUID,
    decision_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: CollaborationServiceDependency,
) -> CollaborationTokenResponse:
    return await execute_collaboration_action(
        lambda: service.issue_token(current_user, workspace_id, decision_id, proposal_id)
    )
