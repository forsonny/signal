"""Tests for core protocol definitions."""

import asyncio
from unittest.mock import AsyncMock

from signalagent.core.protocols import AILayerProtocol, RunnerProtocol, ToolExecutor, WorktreeProxyProtocol, EmbeddingProtocol


class TestAILayerProtocol:
    def test_async_mock_satisfies_protocol(self):
        """An AsyncMock with the right shape satisfies the protocol."""
        mock = AsyncMock()
        mock.complete = AsyncMock()
        assert isinstance(mock, AILayerProtocol)

    def test_object_without_complete_fails(self):
        class Bad:
            pass
        assert not isinstance(Bad(), AILayerProtocol)


class TestRunnerProtocol:
    def test_async_mock_satisfies_protocol(self):
        mock = AsyncMock()
        mock.run = AsyncMock()
        assert isinstance(mock, RunnerProtocol)


class TestToolExecutor:
    def test_async_callable_satisfies_protocol(self):
        mock = AsyncMock()
        assert isinstance(mock, ToolExecutor)


class TestMemoryReaderProtocol:
    def test_memory_engine_satisfies_protocol(self):
        """MemoryEngine must satisfy MemoryReaderProtocol at import time."""
        from signalagent.core.protocols import MemoryReaderProtocol
        from signalagent.memory.engine import MemoryEngine
        # issubclass used here because MemoryEngine requires a Path to construct;
        # runtime_checkable validates method presence on the class itself.
        assert issubclass(MemoryEngine, MemoryReaderProtocol)


class TestRunnerProtocolHistory:
    def test_runner_with_history_satisfies_protocol(self):
        """AgenticRunner with history parameter satisfies RunnerProtocol."""
        from signalagent.runtime.runner import AgenticRunner
        from signalagent.core.protocols import RunnerProtocol
        assert issubclass(AgenticRunner, RunnerProtocol)


class TestEmbeddingProtocol:
    def test_async_mock_satisfies_protocol(self):
        from signalagent.core.protocols import EmbeddingProtocol
        mock = AsyncMock()
        mock.embed = AsyncMock()
        assert isinstance(mock, EmbeddingProtocol)

    def test_object_without_embed_fails(self):
        from signalagent.core.protocols import EmbeddingProtocol
        class Bad:
            pass
        assert not isinstance(Bad(), EmbeddingProtocol)


class _FakeWorktreeProxy:
    def __init__(self):
        self._lock = asyncio.Lock()

    def take_result(self):
        return None

    def task_lock(self):
        return self._lock


class TestWorktreeProxyProtocol:
    def test_structural_subtyping(self) -> None:
        proxy = _FakeWorktreeProxy()
        assert isinstance(proxy, WorktreeProxyProtocol)
