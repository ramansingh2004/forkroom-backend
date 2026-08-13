from uuid import UUID

from fastapi import HTTPException, status

from app.core.exceptions import (
    IntegrationAccessDeniedError,
    IntegrationConfigurationError,
    IntegrationNotFoundError,
    IntegrationProviderError,
    IntegrationProviderUnavailableError,
    WorkspaceNotFoundError,
)
from app.models.integration import IntegrationProvider
from app.models.user import User
from app.schemas.integration import (
    IntegrationAuthorizationResponse,
    IntegrationAuthorizeRequest,
    IntegrationConnectionListResponse,
    IntegrationConnectionResponse,
    IntegrationDeliveryListResponse,
    IntegrationDeliveryResponse,
    IntegrationDestinationListResponse,
    IntegrationDestinationResponse,
    IntegrationProviderListResponse,
    IntegrationProviderResponse,
    IntegrationSubscriptionListResponse,
    IntegrationSubscriptionResponse,
    IntegrationSubscriptionsUpdateRequest,
    IntegrationTestRequest,
    IntegrationTestResponse,
)
from app.services.integration import IntegrationService


def _raise_integration_error(error: Exception) -> None:
    if isinstance(error, WorkspaceNotFoundError):
        raise HTTPException(status_code=404, detail="Workspace not found") from error
    if isinstance(error, IntegrationNotFoundError):
        raise HTTPException(status_code=404, detail="Integration connection not found") from error
    if isinstance(error, IntegrationAccessDeniedError):
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners and admins can manage integrations",
        ) from error
    if isinstance(error, IntegrationProviderUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration provider is not configured",
        ) from error
    if isinstance(error, IntegrationConfigurationError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, IntegrationProviderError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    raise error


def list_integration_providers(service: IntegrationService) -> IntegrationProviderListResponse:
    return IntegrationProviderListResponse(
        items=[
            IntegrationProviderResponse(
                provider=provider.provider,
                name=provider.name,
                description=provider.description,
                available=available,
                capabilities=list(provider.capabilities) if available else [],
            )
            for provider, available in service.provider_catalog()
        ]
    )


async def list_workspace_integrations(
    workspace_id: UUID,
    current_user: User,
    service: IntegrationService,
) -> IntegrationConnectionListResponse:
    try:
        connections = await service.list_connections(current_user, workspace_id)
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationConnectionListResponse(
        items=[IntegrationConnectionResponse.model_validate(item) for item in connections]
    )


async def get_workspace_integration(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: User,
    service: IntegrationService,
) -> IntegrationConnectionResponse:
    try:
        connection = await service.get_connection(current_user, workspace_id, connection_id)
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationConnectionResponse.model_validate(connection)


async def authorize_integration(
    workspace_id: UUID,
    provider: IntegrationProvider,
    payload: IntegrationAuthorizeRequest,
    current_user: User,
    service: IntegrationService,
) -> IntegrationAuthorizationResponse:
    try:
        authorization_url, expires_at = await service.authorize(
            current_user,
            workspace_id,
            provider,
            payload.return_path,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationAuthorizationResponse(
        authorization_url=authorization_url,
        expires_at=expires_at,
    )


async def list_integration_destinations(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: User,
    service: IntegrationService,
) -> IntegrationDestinationListResponse:
    try:
        destinations = await service.list_destinations(
            current_user,
            workspace_id,
            connection_id,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationDestinationListResponse(
        items=[
            IntegrationDestinationResponse(id=item.id, name=item.name, type=item.type)
            for item in destinations
        ]
    )


async def list_integration_subscriptions(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: User,
    service: IntegrationService,
) -> IntegrationSubscriptionListResponse:
    try:
        subscriptions = await service.list_subscriptions(
            current_user,
            workspace_id,
            connection_id,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationSubscriptionListResponse(
        items=[IntegrationSubscriptionResponse.model_validate(item) for item in subscriptions]
    )


async def update_integration_subscriptions(
    workspace_id: UUID,
    connection_id: UUID,
    payload: IntegrationSubscriptionsUpdateRequest,
    current_user: User,
    service: IntegrationService,
) -> IntegrationSubscriptionListResponse:
    try:
        subscriptions = await service.update_subscriptions(
            current_user,
            workspace_id,
            connection_id,
            payload.items,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationSubscriptionListResponse(
        items=[IntegrationSubscriptionResponse.model_validate(item) for item in subscriptions]
    )


async def test_integration(
    workspace_id: UUID,
    connection_id: UUID,
    payload: IntegrationTestRequest,
    current_user: User,
    service: IntegrationService,
) -> IntegrationTestResponse:
    try:
        await service.send_test(
            current_user,
            workspace_id,
            connection_id,
            payload.destination_id,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationTestResponse(delivered=True)


async def list_integration_deliveries(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: User,
    service: IntegrationService,
    *,
    limit: int,
    offset: int,
) -> IntegrationDeliveryListResponse:
    try:
        deliveries = await service.list_deliveries(
            current_user,
            workspace_id,
            connection_id,
            limit=limit,
            offset=offset,
        )
    except Exception as error:
        _raise_integration_error(error)
        raise
    return IntegrationDeliveryListResponse(
        items=[IntegrationDeliveryResponse.model_validate(item) for item in deliveries]
    )


async def disconnect_integration(
    workspace_id: UUID,
    connection_id: UUID,
    current_user: User,
    service: IntegrationService,
) -> None:
    try:
        await service.disconnect(current_user, workspace_id, connection_id)
    except Exception as error:
        _raise_integration_error(error)
