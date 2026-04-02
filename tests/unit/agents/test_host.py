"""Unit tests for AgentHost -- real bus, stub agents."""

import pytest
from unittest.mock import AsyncMock

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import AgentStatus, AgentType, MessageType


class StubAgent(BaseAgent):
    """Minimal agent that echoes back."""

    async def _handle(self, message: Message) -> Message | None:
        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=f"echo: {message.content}",
        )


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def host(bus: MessageBus) -> AgentHost:
    return AgentHost(bus)


class TestRegister:
    def test_register_sets_active(self, host: AgentHost):
        agent = StubAgent(name="agent-a", agent_type=AgentType.MICRO)
        host.register(agent, talks_to={"agent-b"})
        assert agent.status == AgentStatus.ACTIVE

    def test_get_returns_registered_agent(self, host: AgentHost):
        agent = StubAgent(name="agent-a", agent_type=AgentType.MICRO)
        host.register(agent)
        assert host.get("agent-a") is agent

    def test_get_returns_none_for_unknown(self, host: AgentHost):
        assert host.get("unknown") is None

    @pytest.mark.asyncio
    async def test_registered_agent_receives_messages(self, host: AgentHost, bus: MessageBus):
        agent = StubAgent(name="agent-a", agent_type=AgentType.MICRO)
        host.register(agent, talks_to=None)

        bus.register("sender", AsyncMock(), talks_to={"agent-a"})

        msg = Message(
            type=MessageType.TASK,
            sender="sender",
            recipient="agent-a",
            content="hello",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "echo: hello"


class TestListMicroAgents:
    def test_returns_only_micro_agents(self, host: AgentHost):
        micro = StubAgent(name="micro-a", agent_type=AgentType.MICRO)
        prime = StubAgent(name="prime", agent_type=AgentType.PRIME)
        host.register(micro)
        host.register(prime, talks_to=None)

        micros = host.list_micro_agents()
        assert len(micros) == 1
        assert micros[0].name == "micro-a"

    def test_returns_empty_when_no_micros(self, host: AgentHost):
        prime = StubAgent(name="prime", agent_type=AgentType.PRIME)
        host.register(prime, talks_to=None)

        assert host.list_micro_agents() == []


class TestListMicroAgentsIncludesKeeper:
    def test_includes_memory_keeper_type(self, host: AgentHost):
        micro = StubAgent(name="code-review", agent_type=AgentType.MICRO)
        keeper = StubAgent(name="memory-keeper", agent_type=AgentType.MEMORY_KEEPER)

        host.register(micro)
        host.register(keeper)

        agents = host.list_micro_agents()
        names = {a.name for a in agents}
        assert "code-review" in names
        assert "memory-keeper" in names


class TestUnregister:
    def test_unregister_sets_archived(self, host: AgentHost):
        agent = StubAgent(name="agent-a", agent_type=AgentType.MICRO)
        host.register(agent)
        host.unregister("agent-a")

        assert agent.status == AgentStatus.ARCHIVED
        assert host.get("agent-a") is None

    def test_unregister_unknown_is_noop(self, host: AgentHost):
        host.unregister("unknown")
