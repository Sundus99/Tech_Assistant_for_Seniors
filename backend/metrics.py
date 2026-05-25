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
                    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL  NOT NULL DEFAULT 0.0,
                    error            TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON requests(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intent ON requests(intent)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a gpt-4o-mini call."""
    return (
        (prompt_tokens / 1_000_000) * INPUT_PRICE_PER_MTOK
        + (completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_MTOK
    )

def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    k = int(round((pct / 100.0) * (len(values) - 1)))
    return round(values[k], 2)