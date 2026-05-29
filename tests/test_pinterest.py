"""Tests for the Pinterest API client using a mocked httpx.AsyncClient."""

from __future__ import annotations

import pytest
import httpx

from backend.pinterest_client import Pin, PinterestClient, _pin_from_payload


class TestAuthorizationUrl:
    def test_includes_required_params(self) -> None:
        client = PinterestClient(client_id="app123",
                                  client_secret="shh",
                                  redirect_uri="https://example.com/cb")
        url = client.authorization_url("state-xyz")
        assert "client_id=app123" in url
        assert "state=state-xyz" in url
        assert "scope=pins%3Aread%2Cboards%3Aread%2Cuser_accounts%3Aread" in url \
               or "pins:read" in url  # tolerate url-encoding
        assert url.startswith("https://www.pinterest.com/oauth/")


class TestPinParsing:
    def test_picks_biggest_image(self) -> None:
        payload = {
            "id": "p1",
            "title": "Scarf",
            "description": "Warm.",
            "link": "https://pin/1",
            "media": {
                "images": {
                    "600x": {"url": "https://img/600.jpg"},
                    "1200x": {"url": "https://img/1200.jpg"},
                }
            },
        }
        pin = _pin_from_payload(payload)
        assert pin.image_url == "https://img/1200.jpg"

    def test_falls_back_through_sizes(self) -> None:
        payload = {"id": "p2", "link": "https://pin/2",
                   "media": {"images": {"600x": {"url": "https://img/s.jpg"}}}}
        pin = _pin_from_payload(payload)
        assert pin.image_url == "https://img/s.jpg"

    def test_missing_media_doesnt_crash(self) -> None:
        pin = _pin_from_payload({"id": "p3"})
        assert pin.id == "p3"
        assert pin.image_url == ""


@pytest.mark.asyncio
class TestHttpMocked:
    """Exercise the HTTP paths by injecting a transport."""

    async def test_exchange_code_happy_path(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/oauth/token")
            return httpx.Response(200, json={
                "access_token": "pat_abc",
                "token_type": "bearer",
            })

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = PinterestClient(client_id="a", client_secret="b",
                                      redirect_uri="x",
                                      http_client=http)
            token = await client.exchange_code("code-123")
            assert token["access_token"] == "pat_abc"

    async def test_search_my_pins_returns_parsed_pins(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/search/pins")
            assert request.headers["Authorization"] == "Bearer pat_abc"
            return httpx.Response(200, json={
                "items": [
                    {"id": "p1", "title": "Knit Hat", "link": "https://pin/1",
                     "media": {"images": {"1200x": {"url": "https://img/1.jpg"}}}},
                    {"id": "p2", "title": "Mittens", "link": "https://pin/2",
                     "media": {"images": {"600x": {"url": "https://img/2.jpg"}}}},
                ]
            })

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = PinterestClient(http_client=http)
            pins = await client.search_my_pins("pat_abc", "knitting")
            assert len(pins) == 2
            assert pins[0].title == "Knit Hat"
            assert pins[0].image_url == "https://img/1.jpg"

    async def test_http_error_bubbles(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = PinterestClient(http_client=http)
            with pytest.raises(httpx.HTTPStatusError):
                await client.search_my_pins("bad_token", "anything")
