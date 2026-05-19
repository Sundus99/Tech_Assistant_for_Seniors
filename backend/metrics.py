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