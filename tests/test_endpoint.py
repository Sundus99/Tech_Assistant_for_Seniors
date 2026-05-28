"""Integration tests for the FastAPI /chat and /metrics endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


class TestChatEndpoint:
    """POST /chat happy-path and routing behaviour."""

    def test_open_website_routes_locally(self, client) -> None:
        resp = client.post("/chat", json={"user_input": "open youtube"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "open web page"
        assert "youtube.com" in body["url"]

    def test_chat_query_hits_llm(self, client) -> None:
        resp = client.post("/chat", json={"user_input": "what is inflation"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "chat"
        assert body["AI"] == "This is a helpful AI answer."

    def test_mock_llm_provider_runs_without_api_key(self, client, monkeypatch) -> None:
        from backend import tech_assistant_for_seniors as app_module

        monkeypatch.setattr(app_module, "LLM_PROVIDER", "mock")
        resp = client.post("/chat", json={"user_input": "what is inflation"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "chat"
        assert "Inflation means prices are going up" in body["AI"]

    def test_search_refusal(self, client) -> None:
        resp = client.post("/chat", json={"user_input": "search for recipes"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "chat"
        assert "can't" in body["AI"].lower() or "cannot" in body["AI"].lower()

    def test_pin_search_without_auth_returns_auth_url(self, client) -> None:
        resp = client.post("/chat", json={
            "user_input": "show me my knitting pins",
            "session_id": "no-token-yet",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "pinterest_auth_required"
        assert body["pinterest_auth_url"].startswith("https://www.pinterest.com/oauth/")

    def test_empty_input_rejected(self, client) -> None:
        resp = client.post("/chat", json={"user_input": ""})
        assert resp.status_code == 422  # pydantic min_length=1

    def test_oversized_input_rejected(self, client) -> None:
        resp = client.post("/chat", json={"user_input": "x" * 3000})
        assert resp.status_code == 422


class TestMetricsEndpoint:
    """GET /metrics exposes aggregate stats."""

    def test_metrics_starts_empty(self, client) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert resp.json()["total_requests"] == 0

    def test_metrics_records_after_chat(self, client) -> None:
        client.post("/chat", json={"user_input": "open youtube"})
        client.post("/chat", json={"user_input": "what is inflation"})
        stats = client.get("/metrics").json()
        assert stats["total_requests"] == 2
        assert stats["local_routed"] == 1
        assert stats["llm_routed"] == 1
        assert stats["local_hit_rate"] == 0.5

    def test_metrics_tracks_tokens_and_cost(self, client) -> None:
        client.post("/chat", json={"user_input": "explain cryptocurrency"})
        stats = client.get("/metrics").json()
        # The mocked OpenAI response has 42 prompt + 88 completion tokens
        assert stats["total_prompt_tokens"] == 42
        assert stats["total_completion_tokens"] == 88
        assert stats["total_cost_usd"] > 0


class TestRoot:
    def test_root_reports_healthy(self, client) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestOAuthCallback:
    """Pinterest OAuth callback exchanges code for token."""

    def test_callback_rejects_unknown_state(self, client) -> None:
        resp = client.get("/auth/callback",
                          params={"code": "abc", "state": "bogus-state"})
        assert resp.status_code == 400

    def test_callback_accepts_valid_state(self, client, monkeypatch) -> None:
        from backend import tech_assistant_for_seniors as app_module

        # Seed a state as if /chat just issued one
        app_module._oauth_states["valid-state"] = 1.0

        async def fake_exchange(code: str) -> dict:
            return {"access_token": "pat_fake_token", "token_type": "bearer"}

        monkeypatch.setattr(app_module.pinterest, "exchange_code", fake_exchange)

        resp = client.get("/auth/callback",
                          params={"code": "real-code", "state": "valid-state"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "connected"
        assert "session_id" in body


class TestPinSearchWithAuth:
    """Once authorised, pin search returns rendered pins."""

    def test_pin_search_returns_pins(self, client, monkeypatch) -> None:
        from backend import tech_assistant_for_seniors as app_module
        from backend.pinterest_client import Pin

        app_module._pinterest_tokens["sess-abc"] = "pat_fake_token"

        async def fake_search(token: str, query: str, page_size: int = 8):
            return [
                Pin(id="p1", title="Knit Hat", description="",
                    image_url="https://img/1.jpg", link="https://pin/1"),
                Pin(id="p2", title="Scarf Pattern", description="",
                    image_url="https://img/2.jpg", link="https://pin/2"),
            ]

        monkeypatch.setattr(app_module.pinterest, "search_my_pins", fake_search)

        resp = client.post("/chat", json={
            "user_input": "show me my knitting pins",
            "session_id": "sess-abc",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "pins"
        assert len(body["pins"]) == 2
        assert body["pins"][0]["title"] == "Knit Hat"
