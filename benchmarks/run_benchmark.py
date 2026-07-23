"""
Benchmark the intent router.

Runs the 100-query evaluation set through the local classifier, measures
latency per query, and reports:
  - local-routing accuracy (predicted 'local' matches ground-truth label)
  - per-intent breakdown
  - latency distribution
  - projected monthly OpenAI cost savings at various traffic volumes

Usage:
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --json results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

# Make backend/ importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.intent_router import IntentType, classify
from backend.metrics import estimate_cost_usd

# Assumptions for the cost-savings projection. These are conservative
# estimates based on typical gpt-4o-mini usage for a helper assistant.
AVG_PROMPT_TOKENS = 40
AVG_COMPLETION_TOKENS = 120


def load_queries(path: Path) -> list[dict]:
    with path.open() as f:
        return json.load(f)["queries"]


def run(queries: list[dict]) -> dict:
    results = []
    latencies_us = []

    for q in queries:
        start = time.perf_counter_ns()
        routed = classify(q["input"])
        elapsed_us = (time.perf_counter_ns() - start) / 1000.0

        latencies_us.append(elapsed_us)
        predicted_local = routed.handled_locally
        expected_intent = q["expected"]
        expected_local = expected_intent != "chat"

        results.append({
            "input": q["input"],
            "expected": expected_intent,
            "predicted_intent": routed.intent.value,
            "predicted_local": predicted_local,
            "correct": (predicted_local == expected_local)
                       and (routed.intent.value == expected_intent
                            or expected_intent == "chat"),
            "latency_us": round(elapsed_us, 2),
        })

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    predicted_local = sum(1 for r in results if r["predicted_local"])
    actually_local = sum(1 for q in queries if q["expected"] != "chat")

    # Confusion: where did we mispredict?
    misses = [r for r in results if not r["correct"]]

    # Latency stats
    p50 = statistics.median(latencies_us)
    p95 = statistics.quantiles(latencies_us, n=20)[18] if len(latencies_us) >= 20 else max(latencies_us)
    mean = statistics.mean(latencies_us)

    # Per-intent accuracy
    per_intent: dict[str, dict] = {}
    for intent in ["open_website", "search_my_pins", "search_refusal", "chat"]:
        subset = [r for r in results if r["expected"] == intent]
        if subset:
            per_intent[intent] = {
                "n": len(subset),
                "accuracy": round(
                    sum(1 for r in subset if r["correct"]) / len(subset), 4
                ),
            }

    # Cost-savings projection at common traffic volumes.
    per_query_cost = estimate_cost_usd(AVG_PROMPT_TOKENS, AVG_COMPLETION_TOKENS)
    local_hit_rate = predicted_local / total
    savings_projections = {}
    for daily_qs in (100, 500, 1000, 5000):
        monthly = daily_qs * 30
        without_routing = monthly * per_query_cost
        with_routing = monthly * (1 - local_hit_rate) * per_query_cost
        savings_projections[f"{daily_qs}_qps_day"] = {
            "monthly_without_routing_usd": round(without_routing, 2),
            "monthly_with_routing_usd": round(with_routing, 2),
            "monthly_saved_usd": round(without_routing - with_routing, 2),
            "reduction_pct": round(local_hit_rate * 100, 1),
        }

    return {
        "total_queries": total,
        "correct": correct,
        "accuracy": round(correct / total, 4),
        "predicted_local_rate": round(predicted_local / total, 4),
        "ground_truth_local_rate": round(actually_local / total, 4),
        "latency_us": {
            "mean": round(mean, 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
        },
        "per_intent_accuracy": per_intent,
        "cost_savings_projection": savings_projections,
        "misclassifications": [
            {"input": m["input"], "expected": m["expected"],
             "got": m["predicted_intent"]}
            for m in misses
        ],
        "confusion": {
            f"{exp}->{pred}": n for (exp, pred), n in Counter(
                (r["expected"], r["predicted_intent"]) for r in results
            ).most_common()
        },
    }



def render_markdown(report: dict) -> str:
    """Return a compact Markdown report for CI artifacts and README snippets."""
    lines = [
        "# GrandAssist Intent Router Benchmark",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Queries evaluated | {report['total_queries']} |",
        f"| Overall accuracy | {report['accuracy'] * 100:.1f}% |",
        f"| Routed locally | {report['predicted_local_rate'] * 100:.1f}% |",
        f"| Ground-truth local | {report['ground_truth_local_rate'] * 100:.1f}% |",
        f"| p95 latency | {report['latency_us']['p95']} us |",
        "",
        "## Per-Intent Results",
        "",
        "| Intent | Correct | Accuracy |",
        "| --- | ---: | ---: |",
    ]
    for intent, stats in report["per_intent_accuracy"].items():
        correct = round(stats["accuracy"] * stats["n"])
        lines.append(f"| {intent} | {correct}/{stats['n']} | {stats['accuracy'] * 100:.1f}% |")

    lines.extend(["", "## Misclassifications", ""])
    if report["misclassifications"]:
        for miss in report["misclassifications"]:
            lines.append(
                f"- `{miss['input']}` expected `{miss['expected']}`, got `{miss['got']}`"
            )
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)

def pretty_print(report: dict) -> None:
    print("=" * 68)
    print("  GrandAssist Intent Router Benchmark")
    print("=" * 68)
    print(f"  Queries evaluated:       {report['total_queries']}")
    print(f"  Overall accuracy:        {report['accuracy'] * 100:.1f}%")
    print(f"  Routed locally:          {report['predicted_local_rate'] * 100:.1f}%")
    print(f"  Ground-truth local:      {report['ground_truth_local_rate'] * 100:.1f}%")
    print()
    print(f"  Latency (microseconds):  mean {report['latency_us']['mean']}  "
          f"p50 {report['latency_us']['p50']}  p95 {report['latency_us']['p95']}")
    print()
    print("  Per-intent accuracy:")
    for intent, stats in report["per_intent_accuracy"].items():
        print(f"    {intent:<20} {stats['accuracy']*100:5.1f}%  (n={stats['n']})")

    print()
    print("  Cost-savings projection (gpt-4o-mini, ~160 tok/query):")
    for scenario, proj in report["cost_savings_projection"].items():
        daily = scenario.split("_")[0]
        print(f"    {daily:>5} queries/day:  ${proj['monthly_saved_usd']:>6.2f}/mo saved  "
              f"({proj['reduction_pct']}% call reduction)")

    if report["misclassifications"]:
        print()
        print(f"  Misclassifications ({len(report['misclassifications'])}):")
        for m in report["misclassifications"][:10]:
            print(f"    '{m['input'][:40]:<40}'  expected={m['expected']:<16} got={m['got']}")

    print("=" * 68)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path,
                        default=Path(__file__).parent / "queries.json")
    parser.add_argument("--json", type=Path, help="Write full report to this file")
    parser.add_argument("--markdown", type=Path, help="Write Markdown report to this file")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    report = run(queries)
    pretty_print(report)

    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
        print(f"\n  Full report written to {args.json}")

    if args.markdown:
        args.markdown.write_text(render_markdown(report))
        print(f"\n  Markdown report written to {args.markdown}")

    return 0 if report["accuracy"] >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
