from app.core.config import Settings
from app.core.exceptions import IntegrationProviderUnavailableError
from app.integrations.providers.base import IntegrationProviderClient
from app.integrations.providers.slack import SlackProvider
from app.models.integration import IntegrationProvider


class IntegrationProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        slack = SlackProvider(
            client_id=settings.slack_client_id,
            client_secret=settings.slack_client_secret,
            redirect_uri=settings.slack_redirect_uri,
            bot_scopes=settings.slack_bot_scopes,
            timeout_seconds=settings.integration_http_timeout_seconds,
        )
        self._providers: dict[IntegrationProvider, IntegrationProviderClient] = {
            IntegrationProvider.SLACK: slack,
        }

    def list(self) -> list[IntegrationProviderClient]:
        return list(self._providers.values())

    def get(self, provider: IntegrationProvider) -> IntegrationProviderClient:
        client = self._providers.get(provider)
        if client is None or not client.available:
            raise IntegrationProviderUnavailableError
        return client
