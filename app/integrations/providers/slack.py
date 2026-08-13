from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from app.core.exceptions import (
    IntegrationProviderError,
    IntegrationProviderUnavailableError,
)
from app.integrations.providers.base import ProviderDestination, ProviderInstallation
from app.models.integration import IntegrationProvider


class SlackProvider:
    provider: IntegrationProvider = IntegrationProvider.SLACK
    name: str = "Slack"
    description: str = "Send decision updates to Slack channels."
    capabilities: tuple[str, ...] = ("outbound_notifications", "channel_selection")

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str | None,
        bot_scopes: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._bot_scopes = bot_scopes
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self._client_id and self._client_secret and self._redirect_uri)

    def build_authorization_url(self, *, state: str, code_challenge: str) -> str:
        self._require_available()
        query = urlencode(
            {
                "client_id": cast(str, self._client_id),
                "scope": self._bot_scopes,
                "redirect_uri": cast(str, self._redirect_uri),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"https://slack.com/oauth/v2/authorize?{query}"

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> ProviderInstallation:
        self._require_available()
        payload = await self._request(
            "POST",
            "https://slack.com/api/oauth.v2.access",
            auth=httpx.BasicAuth(
                cast(str, self._client_id),
                cast(str, self._client_secret),
            ),
            data={
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": cast(str, self._redirect_uri),
            },
        )
        access_token = self._required_string(payload, "access_token")
        team = self._required_mapping(payload, "team")
        scopes = [scope for scope in self._string(payload, "scope").split(",") if scope]
        expires_in = payload.get("expires_in")
        expires_at = None
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        configuration: dict[str, object] = {}
        bot_user_id = payload.get("bot_user_id")
        app_id = payload.get("app_id")
        if isinstance(bot_user_id, str):
            configuration["bot_user_id"] = bot_user_id
        if isinstance(app_id, str):
            configuration["app_id"] = app_id
        return ProviderInstallation(
            external_account_id=self._required_string(team, "id"),
            external_account_name=self._required_string(team, "name"),
            access_token=access_token,
            refresh_token=self._optional_string(payload, "refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            configuration=configuration,
        )

    async def verify_connection(self, access_token: str) -> None:
        await self._api("POST", "auth.test", access_token)

    async def list_destinations(self, access_token: str) -> list[ProviderDestination]:
        destinations: list[ProviderDestination] = []
        cursor = ""
        for _ in range(10):
            payload = await self._api(
                "GET",
                "conversations.list",
                access_token,
                params={
                    "types": "public_channel,private_channel",
                    "exclude_archived": "true",
                    "limit": "200",
                    "cursor": cursor,
                },
            )
            channels = payload.get("channels")
            if not isinstance(channels, list):
                raise IntegrationProviderError("Slack returned an invalid channel list")
            for value in channels:
                if not isinstance(value, dict):
                    continue
                channel = cast(dict[str, object], value)
                channel_id = channel.get("id")
                name = channel.get("name")
                if isinstance(channel_id, str) and isinstance(name, str):
                    destination_type = (
                        "private_channel" if channel.get("is_private") is True else "channel"
                    )
                    destinations.append(
                        ProviderDestination(
                            id=channel_id,
                            name=name,
                            type=destination_type,
                        )
                    )
            metadata = payload.get("response_metadata")
            if not isinstance(metadata, dict):
                break
            next_cursor = cast(dict[str, object], metadata).get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return sorted(destinations, key=lambda item: item.name.casefold())

    async def send_test_message(
        self,
        access_token: str,
        destination_id: str,
    ) -> None:
        await self._api(
            "POST",
            "chat.postMessage",
            access_token,
            json={
                "channel": destination_id,
                "text": "ForkRoom is connected. Decision notifications will appear here.",
            },
        )

    async def revoke(self, access_token: str) -> None:
        await self._api("POST", "auth.revoke", access_token)

    async def _api(
        self,
        method: str,
        operation: str,
        access_token: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        return await self._request(
            method,
            f"https://slack.com/api/{operation}",
            headers={"Authorization": f"Bearer {access_token}"},
            **kwargs,
        )

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        try:
            if self._client is not None:
                response = await self._client.request(method, url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.request(method, url, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 429:
                retry_after = error.response.headers.get("Retry-After", "unknown")
                raise IntegrationProviderError(
                    f"Slack rate limit reached; retry after {retry_after} seconds"
                ) from error
            raise IntegrationProviderError(
                f"Slack request failed with HTTP {error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise IntegrationProviderError("Slack could not be reached") from error

        raw_payload = response.json()
        if not isinstance(raw_payload, dict):
            raise IntegrationProviderError("Slack returned an invalid response")
        payload = cast(dict[str, object], raw_payload)
        if payload.get("ok") is not True:
            provider_error = payload.get("error")
            message = provider_error if isinstance(provider_error, str) else "unknown_error"
            raise IntegrationProviderError(f"Slack rejected the request: {message}")
        return payload

    def _require_available(self) -> None:
        if not self.available:
            raise IntegrationProviderUnavailableError

    @staticmethod
    def _required_mapping(payload: dict[str, object], field: str) -> dict[str, object]:
        value = payload.get(field)
        if not isinstance(value, dict):
            raise IntegrationProviderError(f"Slack response is missing {field}")
        return cast(dict[str, object], value)

    @staticmethod
    def _required_string(payload: dict[str, object], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise IntegrationProviderError(f"Slack response is missing {field}")
        return value

    @staticmethod
    def _optional_string(payload: dict[str, object], field: str) -> str | None:
        value = payload.get(field)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _string(payload: dict[str, object], field: str) -> str:
        value = payload.get(field)
        return value if isinstance(value, str) else ""
