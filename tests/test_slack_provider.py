from urllib.parse import parse_qs, urlparse

import httpx

from app.integrations.providers.base import ProviderMessage
from app.integrations.providers.slack import SlackProvider


def make_provider(client: httpx.AsyncClient) -> SlackProvider:
    return SlackProvider(
        client_id="123.456",
        client_secret="secret",
        redirect_uri="https://api.example.com/api/v1/integrations/slack/callback",
        bot_scopes="chat:write,channels:read",
        timeout_seconds=10,
        client=client,
    )


async def test_slack_oauth_exchange_uses_v2_and_pkce() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/oauth.v2.access"
        assert request.headers["Authorization"].startswith("Basic ")
        body = request.content.decode("utf-8")
        assert "code=temporary-code" in body
        assert "code_verifier=pkce-verifier" in body
        return httpx.Response(
            200,
            json={
                "ok": True,
                "access_token": "xoxb-installed-token",
                "scope": "chat:write,channels:read",
                "bot_user_id": "B123",
                "team": {"id": "T123", "name": "ForkRoom Engineering"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        installation = await make_provider(client).exchange_code(
            code="temporary-code",
            code_verifier="pkce-verifier",
        )

    assert installation.external_account_id == "T123"
    assert installation.external_account_name == "ForkRoom Engineering"
    assert installation.access_token == "xoxb-installed-token"
    assert installation.scopes == ["chat:write", "channels:read"]
    assert installation.configuration == {"bot_user_id": "B123"}


async def test_slack_lists_public_and_private_destinations() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/conversations.list"
        assert request.headers["Authorization"] == "Bearer xoxb-token"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [
                    {"id": "C2", "name": "product", "is_private": False},
                    {"id": "G1", "name": "architecture", "is_private": True},
                ],
                "response_metadata": {"next_cursor": ""},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        destinations = await make_provider(client).list_destinations("xoxb-token")

    assert [(item.id, item.name, item.type) for item in destinations] == [
        ("G1", "architecture", "private_channel"),
        ("C2", "product", "channel"),
    ]


async def test_slack_authorization_url_binds_state_and_pkce() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        url = make_provider(client).build_authorization_url(
            state="oauth-state",
            code_challenge="pkce-challenge",
        )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "slack.com"
    assert parsed.path == "/oauth/v2/authorize"
    assert query["state"] == ["oauth-state"]
    assert query["code_challenge"] == ["pkce-challenge"]
    assert query["code_challenge_method"] == ["S256"]


async def test_slack_posts_notification_with_idempotency_key() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat.postMessage"
        assert request.headers["Authorization"] == "Bearer xoxb-token"
        payload = request.read().decode("utf-8")
        assert '"channel":"C123"' in payload
        assert '"client_msg_id":"delivery-id"' in payload
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await make_provider(client).send_message(
            "xoxb-token",
            "C123",
            ProviderMessage(
                text="Decision activated",
                idempotency_key="delivery-id",
            ),
        )
