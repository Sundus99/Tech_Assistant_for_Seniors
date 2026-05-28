"""Shared pytest fixtures for GrandAssist tests."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure backend package is importable from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Unique SQLite file per test to avoid cross-test contamination."""
    return tmp_path / "test_metrics.db"


@pytest.fixture
def metrics_store(temp_db_path: Path):
    """Fresh MetricsStore bound to a temp DB."""
    from backend.metrics import MetricsStore
    return MetricsStore(temp_db_path)


@pytest.fixture
def mock_openai_response():
    """A canned OpenAI ChatCompletion response with usage info."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = "This is a helpful AI answer."
    mock.usage.prompt_tokens = 42
    mock.usage.completion_tokens = 88
    return mock


@pytest.fixture
def client(monkeypatch, temp_db_path, mock_openai_response):
    """FastAPI TestClient with OpenAI and Pinterest mocked out."""
    monkeypatch.setenv("METRICS_DB", str(temp_db_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # Import *after* env is set so config picks it up.
    from backend import tech_assistant_for_seniors as app_module

    # Swap in a fresh MetricsStore pointed at temp DB
    from backend.metrics import MetricsStore
    app_module.metrics = MetricsStore(temp_db_path)

    # Mock OpenAI
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = mock_openai_response
    app_module.openai_client = mock_openai

    return TestClient(app_module.app)
