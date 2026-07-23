"""
Metrics collection for GrandAssist.

Logs every request to a local SQLite DB so we can compute:
  - local-routing hit rate (% of queries resolved without an LLM call)
  - p50/p95 latency by path (local vs LLM)
  - total and per-query OpenAI token spend
  - estimated cost in USD

The schema is intentionally simple — single append-only table, queryable with
vanilla SQL, no ORM. We want this to be boringly reliable.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional


# OpenAI gpt-4o-mini pricing (USD per 1M tokens) as of 2025.
# Source: https://openai.com/api/pricing/
INPUT_PRICE_PER_MTOK = 0.15
OUTPUT_PRICE_PER_MTOK = 0.60


@dataclass
class RequestRecord:
    """One row in the request log."""

    ts: float  # unix seconds
    user_input: str
    intent: str
    handled_locally: bool
    latency_ms: float
    outcome: str = "success"
    provider: str = "local"
    response_type: str = "chat"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    error: Optional[str] = None


class MetricsStore:
    """Thread-safe SQLite wrapper for request metrics."""

    def __init__(self, db_path: str | Path = "grandassist_metrics.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts               REAL    NOT NULL,
                    user_input       TEXT    NOT NULL,
                    intent           TEXT    NOT NULL,
                    handled_locally  INTEGER NOT NULL,
                    latency_ms       REAL    NOT NULL,
                    outcome          TEXT    NOT NULL DEFAULT 'success',
                    provider         TEXT    NOT NULL DEFAULT 'local',
                    response_type    TEXT    NOT NULL DEFAULT 'chat',
                    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL  NOT NULL DEFAULT 0.0,
                    error            TEXT
                )
                """
            )
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(requests)")
            }
            migrations = (
                ("outcome", "ALTER TABLE requests ADD COLUMN outcome TEXT NOT NULL DEFAULT 'success'"),
                ("provider", "ALTER TABLE requests ADD COLUMN provider TEXT NOT NULL DEFAULT 'local'"),
                ("response_type", "ALTER TABLE requests ADD COLUMN response_type TEXT NOT NULL DEFAULT 'chat'"),
            )
            for name, ddl in migrations:
                if name not in existing_cols:
                    conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON requests(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intent ON requests(intent)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON requests(outcome)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_provider ON requests(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_response_type ON requests(response_type)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, rec: RequestRecord) -> None:
        """Insert one row. Thread-safe."""
        with self._lock, self._connect() as conn:
            data = asdict(rec)
            data["handled_locally"] = int(data["handled_locally"])
            conn.execute(
                """
                INSERT INTO requests (
                    ts, user_input, intent, handled_locally, latency_ms,
                    outcome, provider, response_type, prompt_tokens,
                    completion_tokens, estimated_cost_usd, error
                ) VALUES (
                    :ts, :user_input, :intent, :handled_locally, :latency_ms,
                    :outcome, :provider, :response_type, :prompt_tokens,
                    :completion_tokens, :estimated_cost_usd, :error
                )
                """,
                data,
            )

    def summary(self) -> dict:
        """Aggregate stats across all recorded requests."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                     AS total,
                    SUM(handled_locally)                         AS local_hits,
                    AVG(CASE WHEN handled_locally=1 THEN latency_ms END) AS local_avg_ms,
                    AVG(CASE WHEN handled_locally=0 THEN latency_ms END) AS llm_avg_ms,
                    SUM(prompt_tokens)                           AS total_prompt_tok,
                    SUM(completion_tokens)                       AS total_completion_tok,
                    SUM(estimated_cost_usd)                      AS total_cost_usd,
                    SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS error_count
                FROM requests
                """
            ).fetchone()

            # Per-intent breakdown
            intents = conn.execute(
                "SELECT intent, COUNT(*) AS n FROM requests GROUP BY intent ORDER BY n DESC"
            ).fetchall()
            outcomes = conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM requests GROUP BY outcome ORDER BY n DESC"
            ).fetchall()
            providers = conn.execute(
                "SELECT provider, COUNT(*) AS n FROM requests GROUP BY provider ORDER BY n DESC"
            ).fetchall()
            response_types = conn.execute(
                "SELECT response_type, COUNT(*) AS n FROM requests GROUP BY response_type ORDER BY n DESC"
            ).fetchall()

            # p95 latency (use Python since SQLite lacks percentile_cont)
            latencies = [r[0] for r in conn.execute(
                "SELECT latency_ms FROM requests ORDER BY latency_ms").fetchall()]

        total = row["total"] or 0
        local_hits = row["local_hits"] or 0

        return {
            "total_requests": total,
            "local_routed": local_hits,
            "llm_routed": total - local_hits,
            "local_hit_rate": (local_hits / total) if total else 0.0,
            "avg_latency_local_ms": round(row["local_avg_ms"] or 0.0, 2),
            "avg_latency_llm_ms": round(row["llm_avg_ms"] or 0.0, 2),
            "p95_latency_ms": _percentile(latencies, 95),
            "total_prompt_tokens": row["total_prompt_tok"] or 0,
            "total_completion_tokens": row["total_completion_tok"] or 0,
            "total_cost_usd": round(row["total_cost_usd"] or 0.0, 4),
            "error_count": row["error_count"] or 0,
            "per_intent": {r["intent"]: r["n"] for r in intents},
            "per_outcome": {r["outcome"]: r["n"] for r in outcomes},
            "per_provider": {r["provider"]: r["n"] for r in providers},
            "per_response_type": {r["response_type"]: r["n"] for r in response_types},
        }


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    k = int(round((pct / 100.0) * (len(values) - 1)))
    return round(values[k], 2)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a gpt-4o-mini call."""
    return (
        (prompt_tokens / 1_000_000) * INPUT_PRICE_PER_MTOK
        + (completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_MTOK
    )


@contextmanager
def timer_ms() -> Iterator[list[float]]:
    """Context manager that yields a one-element list whose [0] is elapsed ms."""
    start = time.perf_counter()
    out: list[float] = [0.0]
    try:
        yield out
    finally:
        out[0] = (time.perf_counter() - start) * 1000.0
