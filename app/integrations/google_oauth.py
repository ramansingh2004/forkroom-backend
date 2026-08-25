from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.exceptions import GoogleOAuthProfileInvalidError, GoogleOAuthProviderError


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    subject: str
    email: str
    email_verified: bool
    display_name: str
    avatar_url: str | None


class GoogleOAuthClient:
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        client_id, _, redirect_uri = self._credentials()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": self._settings.google_oauth_scopes,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{self.AUTHORIZATION_URL}?{query}"

    async def exchange_code(self, code: str, code_verifier: str) -> GoogleProfile:
        client_id, client_secret, redirect_uri = self._credentials()
        token_response = await self._request(
            "POST",
            self.TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        access_token = self._required_string(token_response, "access_token")
        profile = await self._request(
            "GET",
            self.USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        subject = self._required_string(profile, "sub")
        email = self._required_string(profile, "email").lower()
        verified = profile.get("email_verified")
        if verified is not True:
            raise GoogleOAuthProfileInvalidError
        display_name = self._optional_string(profile, "name") or email.split("@", 1)[0]
        avatar_url = self._optional_string(profile, "picture")
        if len(subject) > 255 or len(email) > 320 or len(display_name) > 100:
            raise GoogleOAuthProfileInvalidError
        if avatar_url is not None and len(avatar_url) > 2048:
            avatar_url = None
        return GoogleProfile(
            subject=subject,
            email=email,
            email_verified=True,
            display_name=display_name,
            avatar_url=avatar_url,
        )

    def _credentials(self) -> tuple[str, str, str]:
        values = (
            self._settings.google_oauth_client_id,
            self._settings.google_oauth_client_secret,
            self._settings.google_oauth_redirect_uri,
        )
        if not all(isinstance(value, str) and value.strip() for value in values):
            from app.core.exceptions import GoogleOAuthNotConfiguredError

            raise GoogleOAuthNotConfiguredError
        return cast(tuple[str, str, str], values)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        try:
            if self._http_client is not None:
                response = await self._http_client.request(
                    method,
                    url,
                    data=data,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.google_oauth_http_timeout_seconds
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        data=data,
                        headers=headers,
                    )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GoogleOAuthProviderError from error
        if not isinstance(payload, dict):
            raise GoogleOAuthProviderError
        return cast(dict[str, object], payload)

    @staticmethod
    def _required_string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise GoogleOAuthProfileInvalidError
        return value

    @staticmethod
    def _optional_string(payload: dict[str, object], key: str) -> str | None:
        value = payload.get(key)
        return value if isinstance(value, str) and value else None
