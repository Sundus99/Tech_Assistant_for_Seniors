"""Summarize pytest and coverage output for quick test triage."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

_STATUS_RE = re.compile(r"(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed)")


def parse_pytest_summary(text: str) -> dict[str, int]:
    """Extract pytest terminal status counts from summary text."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for amount, status in _STATUS_RE.findall(text):
        key = "errors" if status == "error" else status
        counts[key] = counts.get(key, 0) + int(amount)
    return counts


def parse_coverage_percent(path: Path) -> float | None:
    """Read coverage.py XML and return line coverage percent."""
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    return round(float(root.attrib.get("line-rate", 0.0)) * 100, 2)


def summarize(pytest_output: str, coverage_xml: Path) -> dict:
    counts = parse_pytest_summary(pytest_output)
    total = sum(counts.values())
    return {
        "total_reported": total,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "errors": counts.get("errors", 0),
        "coverage_percent": parse_coverage_percent(coverage_xml),
        "green": counts.get("failed", 0) == 0 and counts.get("errors", 0) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-output", type=Path, required=True)
    parser.add_argument("--coverage-xml", type=Path, default=Path("coverage.xml"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    report = summarize(args.pytest_output.read_text(), args.coverage_xml)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n")
    return 0 if report["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
