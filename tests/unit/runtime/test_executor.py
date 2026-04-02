"""Unit tests for Executor -- bus-based, mock bus."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from signalagent.core.models import Message, Turn
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


class TestSessionAwareExecutor:
    @pytest.mark.asyncio
    async def test_run_with_session_loads_history(self):
        """Session ID causes history to be loaded and passed in message."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        now = datetime.now(timezone.utc)
        mock_sm.load.return_value = [
            Turn(role="user", content="prior", timestamp=now),
            Turn(role="assistant", content="prior reply", timestamp=now),
        ]

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("new message", session_id="ses_test0001")

        assert result.content == "reply"
        sent_msg = mock_bus.send.call_args[0][0]
        assert len(sent_msg.history) == 2
        assert sent_msg.history[0]["role"] == "user"
        assert sent_msg.history[0]["content"] == "prior"

    @pytest.mark.asyncio
    async def test_run_with_session_appends_turns(self):
        """Successful run appends user and assistant turns to session."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="agent reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        mock_sm.load.return_value = []

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        await executor.run("hello", session_id="ses_test0001")

        assert mock_sm.append.call_count == 2
        user_turn = mock_sm.append.call_args_list[0][0][1]
        assert user_turn.role == "user"
        assert user_turn.content == "hello"
        assistant_turn = mock_sm.append.call_args_list[1][0][1]
        assert assistant_turn.role == "assistant"
        assert assistant_turn.content == "agent reply"

    @pytest.mark.asyncio
    async def test_run_without_session_no_persistence(self):
        """No session_id means no history loaded, no turns appended."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("hello")

        assert result.content == "reply"
        mock_sm.load.assert_not_called()
        mock_sm.append.assert_not_called()
        sent_msg = mock_bus.send.call_args[0][0]
        assert sent_msg.history == []

    @pytest.mark.asyncio
    async def test_run_error_does_not_persist_turns(self):
        """If the bus call fails, no turns are appended to session."""
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(side_effect=Exception("bus error"))

        mock_sm = MagicMock()
        mock_sm.load.return_value = []

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("hello", session_id="ses_test0001")

        assert result.error is not None
        mock_sm.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_backward_compatible_no_session_manager(self):
        """Executor without session_manager works exactly as before."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        executor = Executor(bus=mock_bus)
        result = await executor.run("hello")

        assert result.content == "reply"
