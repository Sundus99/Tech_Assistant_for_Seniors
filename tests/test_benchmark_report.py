"""Tests for benchmark report formatting."""

from __future__ import annotations

from benchmarks.run_benchmark import render_markdown, run


def test_markdown_report_includes_per_intent_results() -> None:
    report = run([
        {"input": "open youtube", "expected": "open_website"},
        {"input": "what is inflation", "expected": "chat"},
    ])

    markdown = render_markdown(report)

    assert "GrandAssist Intent Router Benchmark" in markdown
    assert "| open_website | 1/1 | 100.0% |" in markdown
    assert "| chat | 1/1 | 100.0% |" in markdown
    assert "None." in markdown
