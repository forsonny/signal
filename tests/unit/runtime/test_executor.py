"""Unit tests for Executor -- bus-based, mock bus."""

import pytest
from unittest.mock import AsyncMock

from signalagent.core.models import Message
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT
from signalagent.runtime.executor import Executor, ExecutorResult


class TestExecutorResult:
    def test_success(self):
        result = ExecutorResult(content="Hello!")
        assert result.content == "Hello!"
        assert result.error is None
        assert result.error_type is None

    def test_error(self):
        result = ExecutorResult(content="", error="broke", error_type="RuntimeError")
        assert result.error == "broke"
        assert result.error_type == "RuntimeError"


class TestExecutor:
    @pytest.mark.asyncio
    async def test_run_sends_to_prime_and_returns_content(self):
        response_msg = Message(
            type=MessageType.RESULT,
            sender=PRIME_AGENT,
            recipient=USER_SENDER,
            content="Hello from Prime!",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        executor = Executor(bus=mock_bus)
        result = await executor.run("hello")

        assert result.content == "Hello from Prime!"
        assert result.error is None

        sent_msg = mock_bus.send.call_args[0][0]
        assert sent_msg.sender == USER_SENDER
        assert sent_msg.recipient == PRIME_AGENT
        assert sent_msg.content == "hello"
        assert sent_msg.type == MessageType.TASK

    @pytest.mark.asyncio
    async def test_run_handles_none_response(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=None)

        executor = Executor(bus=mock_bus)
        result = await executor.run("hello")

        assert result.content == ""
        assert result.error is not None
        assert "No response" in result.error

    @pytest.mark.asyncio
    async def test_run_error_boundary(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(side_effect=Exception("bus exploded"))

        executor = Executor(bus=mock_bus)
        result = await executor.run("hello")

        assert result.content == ""
        assert "bus exploded" in result.error
        assert result.error_type == "Exception"
