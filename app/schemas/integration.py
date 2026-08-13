from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.integration import (
    IntegrationConnectionStatus,
    IntegrationDeliveryStatus,
    IntegrationEventType,
    IntegrationProvider,
)


class IntegrationProviderResponse(BaseModel):
    provider: IntegrationProvider
    name: str
    description: str
    available: bool
    capabilities: list[str]


class IntegrationProviderListResponse(BaseModel):
    items: list[IntegrationProviderResponse]


class IntegrationConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    provider: IntegrationProvider
    status: IntegrationConnectionStatus
    external_account_id: str
    external_account_name: str
    scopes: list[str]
    configuration: dict[str, object]
    connected_by_id: UUID
    token_expires_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class IntegrationConnectionListResponse(BaseModel):
    items: list[IntegrationConnectionResponse]


class IntegrationAuthorizeRequest(BaseModel):
    return_path: str | None = Field(default=None, max_length=500)

    @field_validator("return_path")
    @classmethod
    def validate_return_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
            or "?" in value
            or "#" in value
        ):
            raise ValueError("Return path must be an application-relative path")
        return value


class IntegrationAuthorizationResponse(BaseModel):
    authorization_url: str
    expires_at: datetime


class IntegrationDestinationResponse(BaseModel):
    id: str
    name: str
    type: str


class IntegrationDestinationListResponse(BaseModel):
    items: list[IntegrationDestinationResponse]


class IntegrationSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    event_type: IntegrationEventType
    enabled: bool
    destination_id: str | None
    destination_name: str | None
    configuration: dict[str, object]
    created_at: datetime
    updated_at: datetime


class IntegrationSubscriptionListResponse(BaseModel):
    items: list[IntegrationSubscriptionResponse]


class IntegrationSubscriptionUpdate(BaseModel):
    event_type: IntegrationEventType
    enabled: bool
    destination_id: str | None = Field(default=None, max_length=255)
    destination_name: str | None = Field(default=None, max_length=255)
    configuration: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enabled_subscription_requires_destination(self) -> "IntegrationSubscriptionUpdate":
        if self.enabled and (not self.destination_id or not self.destination_name):
            raise ValueError("Enabled subscriptions require a destination")
        return self


class IntegrationSubscriptionsUpdateRequest(BaseModel):
    items: list[IntegrationSubscriptionUpdate] = Field(min_length=1, max_length=20)

    @field_validator("items")
    @classmethod
    def reject_duplicate_events(
        cls,
        value: list[IntegrationSubscriptionUpdate],
    ) -> list[IntegrationSubscriptionUpdate]:
        event_types = [item.event_type for item in value]
        if len(event_types) != len(set(event_types)):
            raise ValueError("Subscription event types must be unique")
        return value


class IntegrationTestRequest(BaseModel):
    destination_id: str | None = Field(default=None, max_length=255)


class IntegrationTestResponse(BaseModel):
    delivered: bool


class IntegrationDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    event_type: IntegrationEventType
    event_id: UUID
    status: IntegrationDeliveryStatus
    attempt_count: int
    error_code: str | None
    next_retry_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IntegrationDeliveryListResponse(BaseModel):
    items: list[IntegrationDeliveryResponse]
