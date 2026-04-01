"""Unit tests for BaseAgent -- status transitions via template method."""

import pytest

from signalagent.agents.base import BaseAgent
from signalagent.core.models import Message
from signalagent.core.types import AgentStatus, AgentType, MessageType


def _make_message(content: str = "test") -> Message:
    return Message(
        type=MessageType.TASK,
        sender="user",
        recipient="test-agent",
        content=content,
    )


class StubAgent(BaseAgent):
    """Concrete subclass that returns a simple response."""

    async def _handle(self, message: Message) -> Message | None:
        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=f"handled: {message.content}",
        )


class FailingAgent(BaseAgent):
    """Concrete subclass that raises during _handle."""

    async def _handle(self, message: Message) -> Message | None:
        raise RuntimeError("agent exploded")


class TestBaseAgent:
    def test_initial_status_is_created(self):
        agent = StubAgent(name="test", agent_type=AgentType.MICRO)
        assert agent.status == AgentStatus.CREATED

    def test_default_skill_is_empty(self):
        agent = StubAgent(name="test", agent_type=AgentType.MICRO)
        assert agent.skill == ""

    @pytest.mark.asyncio
    async def test_handle_sets_busy_then_idle(self):
        agent = StubAgent(name="test", agent_type=AgentType.MICRO)
        agent.status = AgentStatus.ACTIVE

        result = await agent.handle(_make_message())

        assert result is not None
        assert result.content == "handled: test"
        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_handle_sets_idle_on_error(self):
        agent = FailingAgent(name="test", agent_type=AgentType.MICRO)
        agent.status = AgentStatus.ACTIVE

        with pytest.raises(RuntimeError, match="agent exploded"):
            await agent.handle(_make_message())

        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_base_handle_raises_not_implemented(self):
        agent = BaseAgent(name="test", agent_type=AgentType.MICRO)

        with pytest.raises(NotImplementedError):
            await agent.handle(_make_message())

        assert agent.status == AgentStatus.IDLE
