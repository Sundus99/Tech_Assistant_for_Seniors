"""Tests for pytest result summary tooling."""

from __future__ import annotations

from pathlib import Path

from scripts.summarize_tests import (
    parse_coverage_percent,
    parse_pytest_summary,
    summarize,
)


def test_parse_pytest_summary_counts_statuses() -> None:
    text = "=================== 75 passed, 5 skipped, 1 warning in 0.89s ==================="
    assert parse_pytest_summary(text) == {
        "passed": 75,
        "failed": 0,
        "skipped": 5,
        "errors": 0,
    }


def test_parse_pytest_summary_counts_failures_and_errors() -> None:
    text = "FAILED tests/a.py::test_a - boom\n===== 2 failed, 3 passed, 1 error in 1.2s ====="
    assert parse_pytest_summary(text)["failed"] == 2
    assert parse_pytest_summary(text)["errors"] == 1


def test_parse_coverage_percent(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.xml"
    coverage.write_text('<coverage line-rate="0.9402"></coverage>')
    assert parse_coverage_percent(coverage) == 94.02


def test_summarize_marks_red_when_failures_exist(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.xml"
    coverage.write_text('<coverage line-rate="0.5"></coverage>')
    report = summarize("1 failed, 2 passed", coverage)
    assert report["green"] is False
    assert report["coverage_percent"] == 50.0
