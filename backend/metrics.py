from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional

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
                """)