"""
Pinterest API v5 client for GrandAssist.

Implements the minimum surface we need:
  - OAuth 2.0 authorization-code flow (the extension redirects the user here,
    we exchange the code for a token, store it in-memory keyed by user session).
  - Search the signed-in user's saved pins by query term.

Pinterest's public API only lets you search your OWN pins, not all of Pinterest.
This is a feature for our use case: seniors keep losing track of pins they've
already saved.

Docs: https://developers.pinterest.com/docs/api/v5/
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

PINTEREST_API_BASE = "https://api.pinterest.com/v5"
PINTEREST_AUTH_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = f"{PINTEREST_API_BASE}/oauth/token"


@dataclass
class Pin:
    """Minimal pin representation for the sidebar."""

    id: str
    title: str
    description: str
    image_url: str
    link: str


class PinterestClient:
    """Wraps Pinterest v5 calls. Inject ``http_client`` in tests for mocking."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("PINTEREST_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("PINTEREST_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.getenv(
            "PINTEREST_REDIRECT_URI",
            "https://tech-assistant-for-seniors-eb4876783faf.herokuapp.com/auth/callback",
        )
        self._http = http_client

    def authorization_url(self, state: str) -> str:
        """URL to redirect the user to so they can grant pin:read scope."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "pins:read,boards:read,user_accounts:read",
            "state": state,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{PINTEREST_AUTH_URL}?{qs}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Swap an OAuth code for an access token."""
        client = self._http or httpx.AsyncClient()
        try:
            resp = await client.post(
                PINTEREST_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                auth=(self.client_id, self.client_secret),
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
        finally:
            if self._http is None:
                await client.aclose()

    async def search_my_pins(self, access_token: str, query: str,
                             page_size: int = 12) -> list[Pin]:
        """
        Search the authenticated user's own saved pins.

        Uses GET /v5/search/pins with a bearer token.
        """
        client = self._http or httpx.AsyncClient()
        try:
            resp = await client.get(
                f"{PINTEREST_API_BASE}/search/pins",
                params={"query": query, "page_size": page_size},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            return [_pin_from_payload(item) for item in payload.get("items", [])]
        finally:
            if self._http is None:
                await client.aclose()


def _pin_from_payload(item: dict[str, Any]) -> Pin:
    media = item.get("media") or {}
    images = media.get("images") or {}
    # Pick the biggest available image for senior-friendly display.
    best = images.get("1200x") or images.get("600x") or images.get("originals") or {}
    return Pin(
        id=item.get("id", ""),
        title=item.get("title") or item.get("grid_title") or "",
        description=item.get("description") or "",
        image_url=best.get("url", ""),
        link=item.get("link") or f"https://www.pinterest.com/pin/{item.get('id')}/",
    )
