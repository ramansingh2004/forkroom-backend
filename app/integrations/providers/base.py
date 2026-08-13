from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models.integration import IntegrationProvider


@dataclass(frozen=True, slots=True)
class ProviderInstallation:
    external_account_id: str
    external_account_name: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    configuration: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProviderDestination:
    id: str
    name: str
    type: str


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    text: str
    blocks: list[dict[str, object]] | None = None
    idempotency_key: str | None = None


class IntegrationProviderClient(Protocol):
    provider: IntegrationProvider
    name: str
    description: str
    capabilities: tuple[str, ...]

    @property
    def available(self) -> bool: ...

    def build_authorization_url(self, *, state: str, code_challenge: str) -> str: ...

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> ProviderInstallation: ...

    async def verify_connection(self, access_token: str) -> None: ...

    async def list_destinations(self, access_token: str) -> list[ProviderDestination]: ...

    async def send_test_message(
        self,
        access_token: str,
        destination_id: str,
    ) -> None: ...

    async def send_message(
        self,
        access_token: str,
        destination_id: str,
        message: ProviderMessage,
    ) -> None: ...

    async def revoke(self, access_token: str) -> None: ...
