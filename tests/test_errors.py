"""Tests for error paths — OpenAI down, Pinterest errors, bad input."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestOpenAIFailure:
    """When OpenAI raises, we should still return valid JSON and log it."""

    def test_openai_exception_returns_friendly_error(self, client) -> None:
        from backend import tech_assistant_for_seniors as app_module

        # Force the next LLM call to explode
        app_module.openai_client = MagicMock()
        app_module.openai_client.chat.completions.create.side_effect = \
            RuntimeError("API is down")

        resp = client.post("/chat", json={"user_input": "what is inflation"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "error"
        assert "sorry" in body["AI"].lower() or "wrong" in body["AI"].lower()

    def test_openai_failure_recorded_in_metrics(self, client) -> None:
        from backend import tech_assistant_for_seniors as app_module

        app_module.openai_client = MagicMock()
        app_module.openai_client.chat.completions.create.side_effect = \
            RuntimeError("boom")

        client.post("/chat", json={"user_input": "what is cryptography"})
        stats = client.get("/metrics").json()
        assert stats["error_count"] == 1


class TestPinterestFailure:
    def test_pin_search_api_error_returns_friendly_message(self,
                                                            client,
                                                            monkeypatch) -> None:
        from backend import tech_assistant_for_seniors as app_module

        app_module._pinterest_tokens["sess-err"] = "pat_fake"

        async def failing_search(token, query, page_size=8):
            raise RuntimeError("Pinterest returned 503")

        monkeypatch.setattr(app_module.pinterest, "search_my_pins", failing_search)

        resp = client.post("/chat", json={
            "user_input": "show me my knitting pins",
            "session_id": "sess-err",
        })
        assert resp.status_code == 200
        assert resp.json()["type"] == "error"


class TestMalformedInput:
    def test_missing_user_input_field(self, client) -> None:
        resp = client.post("/chat", json={"session_id": "x"})
        assert resp.status_code == 422

    def test_non_json_body(self, client) -> None:
        resp = client.post("/chat", data="not json",
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_wrong_http_method(self, client) -> None:
        resp = client.get("/chat")
        assert resp.status_code == 405
