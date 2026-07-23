"""Unit tests for the metrics module."""

from __future__ import annotations

import time

import pytest

from backend.metrics import (
    INPUT_PRICE_PER_MTOK,
    OUTPUT_PRICE_PER_MTOK,
    MetricsStore,
    RequestRecord,
    _percentile,
    estimate_cost_usd,
    timer_ms,
)


class TestRecordAndSummary:
    def test_empty_store_summary(self, metrics_store: MetricsStore) -> None:
        summary = metrics_store.summary()
        assert summary["total_requests"] == 0
        assert summary["local_hit_rate"] == 0.0
        assert summary["total_cost_usd"] == 0.0

    def test_single_record_appears_in_summary(self,
                                               metrics_store: MetricsStore) -> None:
        metrics_store.record(RequestRecord(
            ts=time.time(),
            user_input="open youtube",
            intent="open_website",
            handled_locally=True,
            latency_ms=2.1,
        ))
        summary = metrics_store.summary()
        assert summary["total_requests"] == 1
        assert summary["local_routed"] == 1
        assert summary["local_hit_rate"] == 1.0

    def test_mixed_records_compute_hit_rate(self,
                                             metrics_store: MetricsStore) -> None:
        # Three local + one LLM
        for intent in ("open_website", "open_website", "search_my_pins"):
            metrics_store.record(RequestRecord(
                ts=time.time(), user_input="x", intent=intent,
                handled_locally=True, latency_ms=1.0,
            ))
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="what is X", intent="chat",
            handled_locally=False, latency_ms=1500.0,
            prompt_tokens=30, completion_tokens=100,
            estimated_cost_usd=estimate_cost_usd(30, 100),
        ))
        summary = metrics_store.summary()
        assert summary["total_requests"] == 4
        assert summary["local_routed"] == 3
        assert summary["local_hit_rate"] == 0.75
        assert summary["total_cost_usd"] > 0

    def test_per_intent_breakdown(self, metrics_store: MetricsStore) -> None:
        for _ in range(2):
            metrics_store.record(RequestRecord(
                ts=time.time(), user_input="x", intent="open_website",
                handled_locally=True, latency_ms=1.0))
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="x", intent="chat",
            handled_locally=False, latency_ms=1000.0))
        summary = metrics_store.summary()
        assert summary["per_intent"] == {"open_website": 2, "chat": 1}

    def test_error_count_tracked(self, metrics_store: MetricsStore) -> None:
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="x", intent="chat",
            handled_locally=False, latency_ms=1.0, outcome="error",
            error="RuntimeError: boom"))
        assert metrics_store.summary()["error_count"] == 1

    def test_outcome_breakdown(self, metrics_store: MetricsStore) -> None:
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="open youtube", intent="open_website",
            handled_locally=True, latency_ms=1.0, outcome="success"))
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="show me my pins", intent="search_my_pins",
            handled_locally=True, latency_ms=1.0, outcome="auth_required"))
        metrics_store.record(RequestRecord(
            ts=time.time(), user_input="what is x", intent="chat",
            handled_locally=False, latency_ms=1.0, outcome="error",
            error="RuntimeError: boom"))

        assert metrics_store.summary()["per_outcome"] == {
            "success": 1,
            "auth_required": 1,
            "error": 1,
        }


class TestCostEstimation:
    def test_zero_tokens_zero_cost(self) -> None:
        assert estimate_cost_usd(0, 0) == 0.0

    def test_known_pricing(self) -> None:
        # 1M input tokens should cost exactly INPUT_PRICE_PER_MTOK
        assert estimate_cost_usd(1_000_000, 0) == pytest.approx(INPUT_PRICE_PER_MTOK)
        assert estimate_cost_usd(0, 1_000_000) == pytest.approx(OUTPUT_PRICE_PER_MTOK)

    def test_mixed_tokens_add_correctly(self) -> None:
        expected = (500_000 / 1_000_000) * INPUT_PRICE_PER_MTOK \
                   + (250_000 / 1_000_000) * OUTPUT_PRICE_PER_MTOK
        assert estimate_cost_usd(500_000, 250_000) == pytest.approx(expected)


class TestPercentile:
    def test_empty_list_returns_zero(self) -> None:
        assert _percentile([], 95) == 0.0

    def test_single_value(self) -> None:
        assert _percentile([5.0], 95) == 5.0

    def test_known_p95(self) -> None:
        values = list(range(1, 101))  # 1..100
        # p95 of 1..100 with this rounding = index 94 -> value 95
        assert _percentile(values, 95) == 95.0

    def test_p50_is_median_ish(self) -> None:
        assert _percentile([1, 2, 3, 4, 5], 50) == 3.0


class TestTimer:
    def test_timer_records_elapsed(self) -> None:
        with timer_ms() as elapsed:
            time.sleep(0.01)
        assert elapsed[0] >= 10.0  # at least 10ms slept
        assert elapsed[0] < 500.0   # not absurd
