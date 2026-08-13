from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from app.controllers.integration import (
    authorize_integration,
    disconnect_integration,
    get_workspace_integration,
    list_integration_destinations,
    list_integration_providers,
    list_integration_subscriptions,
    list_workspace_integrations,
    test_integration,
    update_integration_subscriptions,
)
from app.core.config import get_settings
from app.core.exceptions import IntegrationOAuthStateError
from app.dependencies.auth import get_current_user
from app.dependencies.integration import get_integration_service
from app.models.integration import IntegrationProvider
from app.models.user import User
from app.schemas.integration import (
    IntegrationAuthorizationResponse,
    IntegrationAuthorizeRequest,
    IntegrationConnectionListResponse,
    IntegrationConnectionResponse,
    IntegrationDestinationListResponse,
    IntegrationProviderListResponse,
    IntegrationSubscriptionListResponse,
    IntegrationSubscriptionsUpdateRequest,
    IntegrationTestRequest,
    IntegrationTestResponse,
)
from app.services.integration import IntegrationService

router = APIRouter(tags=["Integrations"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[IntegrationService, Depends(get_integration_service)]


@router.get(
    "/integrations/providers",
    response_model=IntegrationProviderListResponse,
    summary="List integration providers",
)
async def providers(
    _: CurrentUser,
    service: Service,
) -> IntegrationProviderListResponse:
    return list_integration_providers(service)


@router.get(
    "/workspaces/{workspace_id}/integrations",
    response_model=IntegrationConnectionListResponse,
    summary="List workspace integrations",
)
async def list_connections(
    workspace_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationConnectionListResponse:
    return await list_workspace_integrations(workspace_id, current_user, service)


@router.post(
    "/workspaces/{workspace_id}/integrations/{provider}/authorize",
    response_model=IntegrationAuthorizationResponse,
    summary="Start integration OAuth",
)
async def authorize(
    workspace_id: UUID,
    provider: IntegrationProvider,
    payload: IntegrationAuthorizeRequest,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationAuthorizationResponse:
    return await authorize_integration(
        workspace_id,
        provider,
        payload,
        current_user,
        service,
    )


@router.get(
    "/integrations/{provider}/callback",
    response_class=RedirectResponse,
    include_in_schema=True,
    summary="Complete integration OAuth",
)
async def oauth_callback(
    provider: IntegrationProvider,
    service: Service,
    state: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    try:
        redirect_url = await service.complete_authorization(
            provider,
            state=state,
            code=code,
            provider_error=error,
        )
    except IntegrationOAuthStateError:
        redirect_url = (
            f"{get_settings().frontend_url.rstrip('/')}"
            "/integrations?integration_error=invalid_state"
        )
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/workspaces/{workspace_id}/integrations/{connection_id}",
    response_model=IntegrationConnectionResponse,
    summary="Get a workspace integration",
)
async def get_connection(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationConnectionResponse:
    return await get_workspace_integration(
        workspace_id,
        connection_id,
        current_user,
        service,
    )


@router.get(
    "/workspaces/{workspace_id}/integrations/{connection_id}/destinations",
    response_model=IntegrationDestinationListResponse,
    summary="List integration destinations",
)
async def destinations(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationDestinationListResponse:
    return await list_integration_destinations(
        workspace_id,
        connection_id,
        current_user,
        service,
    )


@router.get(
    "/workspaces/{workspace_id}/integrations/{connection_id}/subscriptions",
    response_model=IntegrationSubscriptionListResponse,
    summary="List integration subscriptions",
)
async def subscriptions(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationSubscriptionListResponse:
    return await list_integration_subscriptions(
        workspace_id,
        connection_id,
        current_user,
        service,
    )


@router.patch(
    "/workspaces/{workspace_id}/integrations/{connection_id}/subscriptions",
    response_model=IntegrationSubscriptionListResponse,
    summary="Update integration subscriptions",
)
async def update_subscriptions(
    workspace_id: UUID,
    connection_id: UUID,
    payload: IntegrationSubscriptionsUpdateRequest,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationSubscriptionListResponse:
    return await update_integration_subscriptions(
        workspace_id,
        connection_id,
        payload,
        current_user,
        service,
    )


@router.post(
    "/workspaces/{workspace_id}/integrations/{connection_id}/test",
    response_model=IntegrationTestResponse,
    summary="Send an integration test message",
)
async def test_connection(
    workspace_id: UUID,
    connection_id: UUID,
    payload: IntegrationTestRequest,
    current_user: CurrentUser,
    service: Service,
) -> IntegrationTestResponse:
    return await test_integration(
        workspace_id,
        connection_id,
        payload,
        current_user,
        service,
    )


@router.delete(
    "/workspaces/{workspace_id}/integrations/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect an integration",
)
async def disconnect(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: CurrentUser,
    service: Service,
) -> None:
    await disconnect_integration(workspace_id, connection_id, current_user, service)
