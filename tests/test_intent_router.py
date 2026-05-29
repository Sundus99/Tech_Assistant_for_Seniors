"""Unit tests for the intent router. Pure functions, no network."""

from __future__ import annotations

import pytest

from backend.intent_router import IntentType, classify


class TestOpenWebsite:
    """Queries that should resolve to 'open a known website'."""

    @pytest.mark.parametrize("query,expected_host", [
        ("open youtube",        "youtube.com"),
        ("open you tube",       "youtube.com"),
        ("launch gmail",        "gmail.com"),
        ("go to google",        "google.ca"),
        ("take me to amazon",   "amazon.ca"),
        ("open facebook",       "facebook.com"),
        ("launch wikipedia",    "wikipedia.org"),
        ("open yahoo",          "yahoo.com"),
        ("open bing",           "bing.com"),
        ("go to duck duck go",  "duckduckgo.com"),
        ("launch pinterest",    "pinterest.com"),
        ("take me to outlook",  "outlook"),
    ])
    def test_known_sites(self, query: str, expected_host: str) -> None:
        result = classify(query)
        assert result.intent == IntentType.OPEN_WEBSITE
        assert result.handled_locally is True
        assert expected_host in result.url

    def test_mixed_case(self) -> None:
        assert classify("Open Youtube").intent == IntentType.OPEN_WEBSITE

    def test_trailing_whitespace(self) -> None:
        assert classify("  open gmail  ").intent == IntentType.OPEN_WEBSITE


class TestPinSearch:
    """Queries that should route to Pinterest pin search."""

    @pytest.mark.parametrize("query,expected_term", [
        ("show me my knitting pins",           "knitting pins"),
        ("show me my recipe pins",             "recipe pins"),
        ("find my soup recipes",               "soup recipes"),
        ("my pins of Christmas decorations",   "christmas decorations"),
        ("my saved gardening ideas",           "gardening ideas"),
    ])
    def test_pin_search_extracts_query(self, query: str, expected_term: str) -> None:
        result = classify(query)
        assert result.intent == IntentType.SEARCH_MY_PINS
        assert result.query is not None
        assert expected_term.lower() in result.query.lower()

    def test_empty_pin_query_falls_back(self) -> None:
        """If user trails off ('show me my'), default to 'recent' pins rather than crash."""
        result = classify("show me my")
        assert result.intent == IntentType.SEARCH_MY_PINS
        assert result.query == "recent"


class TestSearchRefusal:
    """Generic web searches should be politely declined."""

    @pytest.mark.parametrize("query", [
        "search for cookie recipes",
        "google the weather",
        "search the web for flu symptoms",
    ])
    def test_refusal(self, query: str) -> None:
        result = classify(query)
        assert result.intent == IntentType.SEARCH_REFUSAL
        assert result.handled_locally is True


class TestLLMFallback:
    """Queries that the local router can't handle."""

    @pytest.mark.parametrize("query", [
        "what is inflation",
        "how do I change my password",
        "tell me a joke",
        "what's the capital of France",
        "explain phishing to me",
    ])
    def test_falls_through_to_chat(self, query: str) -> None:
        result = classify(query)
        assert result.intent == IntentType.CHAT
        assert result.handled_locally is False


class TestEdgeCases:
    """Malformed / edge inputs shouldn't crash."""

    def test_empty_string(self) -> None:
        result = classify("")
        assert result.intent == IntentType.CHAT
        assert "didn't catch" in result.reply.lower() or result.handled_locally

    def test_whitespace_only(self) -> None:
        result = classify("   ")
        assert result.intent == IntentType.CHAT

    def test_howto_about_opening_is_not_open_command(self) -> None:
        """'how do I open X' should go to LLM, not trigger website open."""
        result = classify("how do I open a pdf file")
        assert result.intent == IntentType.CHAT

    def test_howto_about_searching_is_not_search_refusal(self) -> None:
        result = classify("how do I search google effectively")
        assert result.intent == IntentType.CHAT

    def test_very_long_input(self) -> None:
        """Should not explode on a long query."""
        query = "tell me about " + "the weather " * 100
        result = classify(query)
        assert result.intent in {IntentType.CHAT, IntentType.OPEN_WEBSITE}

    def test_unicode_input(self) -> None:
        result = classify("tell me about café culture 🗼")
        assert result.intent == IntentType.CHAT
