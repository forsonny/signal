"""Shared fixtures for TUI tests."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from signalagent.runtime.executor import Executor, ExecutorResult
from signalagent.comms.bus import MessageBus
from signalagent.agents.host import AgentHost


@pytest.fixture
def tmp_instance_dir(tmp_path: Path) -> Path:
    """Create a minimal .signal instance directory for testing."""
    instance_dir = tmp_path / ".signal"
    instance_dir.mkdir()
    sessions_dir = instance_dir / "data" / "sessions"
    sessions_dir.mkdir(parents=True)

    config_yaml = instance_dir / "config.yaml"
    config_yaml.write_text(
        "profile_name: blank\n"
        "ai:\n"
        "  default_model: test-model/test-v1\n"
    )
    return instance_dir


@pytest.fixture
def mock_executor() -> AsyncMock:
    """Mock Executor that returns a successful response."""
    executor = AsyncMock(spec=Executor)
    executor.run.return_value = ExecutorResult(content="Test response.")
    return executor


@pytest.fixture
def patch_bootstrap(monkeypatch, mock_executor):
    """Monkeypatch bootstrap() to return mocked runtime components.

    Patches ``signalagent.runtime.bootstrap.bootstrap`` because app.py
    imports it inside ``on_mount`` via a deferred ``from ... import``.
    """
    mock_bus = MagicMock(spec=MessageBus)
    mock_host = MagicMock(spec=AgentHost)

    async def fake_bootstrap(instance_dir, config, profile):
        return mock_executor, mock_bus, mock_host

    monkeypatch.setattr(
        "signalagent.runtime.bootstrap.bootstrap", fake_bootstrap,
    )
    return mock_executor
