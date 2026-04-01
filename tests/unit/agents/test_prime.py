"""Unit tests for PrimeAgent -- mock AILayer, real bus, stub micro-agents."""

import pytest
from unittest.mock import AsyncMock

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.agents.micro import MicroAgent
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AIResponse
from signalagent.comms.bus import MessageBus
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import (
    AgentType,
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)


def _make_ai_response(content: str) -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


class StubMicro(BaseAgent):
    """Micro-agent stub that echoes content."""

    async def _handle(self, message: Message) -> Message | None:
        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=f"[{self.name}] handled: {message.content}",
            parent_id=message.id,
        )


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def host(bus: MessageBus) -> AgentHost:
    return AgentHost(bus)


def _register_prime(
    host: AgentHost,
    bus: MessageBus,
    mock_ai: AsyncMock,
    identity: str = "You are a test prime.",
) -> PrimeAgent:
    prime = PrimeAgent(identity=identity, ai=mock_ai, host=host, bus=bus)
    host.register(prime, talks_to=None)
    return prime


def _register_stub_micro(host: AgentHost, name: str) -> StubMicro:
    agent = StubMicro(name=name, agent_type=AgentType.MICRO)
    host.register(agent, talks_to={PRIME_AGENT})
    return agent


class TestRouting:
    @pytest.mark.asyncio
    async def test_routes_to_matched_agent(self, host, bus):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="review my code",
        )
        result = await bus.send(msg)

        assert result is not None
        assert "[code-review] handled:" in result.content

    @pytest.mark.asyncio
    async def test_routes_case_insensitive(self, host, bus):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("  Code-Review  "),
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="review my code",
        )
        result = await bus.send(msg)

        assert result is not None
        assert "[code-review] handled:" in result.content


class TestFallbackToDirectHandling:
    @pytest.mark.asyncio
    async def test_none_response_falls_back(self, host, bus):
        """LLM returns NONE -- Prime handles directly."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response("NONE"),
                _make_ai_response("I handled it"),
            ]
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="what is 2+2?",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "I handled it"

    @pytest.mark.asyncio
    async def test_garbage_response_falls_back(self, host, bus):
        """LLM returns unrecognized text -- Prime handles directly."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response("I think maybe code-review or something"),
                _make_ai_response("I handled it"),
            ]
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="what is 2+2?",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "I handled it"

    @pytest.mark.asyncio
    async def test_routing_error_falls_back(self, host, bus):
        """LLM routing call itself fails -- Prime handles directly."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                Exception("LLM timeout"),
                _make_ai_response("I handled it"),
            ]
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="what is 2+2?",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "I handled it"

    @pytest.mark.asyncio
    async def test_no_micro_agents_handles_directly(self, host, bus):
        """No micro-agents registered -- Prime handles directly."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("I handled it"),
        )
        _register_prime(host, bus, mock_ai)

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="hello",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "I handled it"
        assert mock_ai.complete.call_count == 1


class TestDirectHandling:
    @pytest.mark.asyncio
    async def test_uses_prime_identity_prompt(self, host, bus):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("response"),
        )
        _register_prime(host, bus, mock_ai, identity="You are a pirate.")

        msg = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="hello",
        )
        await bus.send(msg)

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        assert call_messages[0]["role"] == "system"
        assert call_messages[0]["content"] == "You are a pirate."


class TestResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_correct_type_and_parent(self, host, bus):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        msg = Message(
            id="msg_original",
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content="review my code",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.type == MessageType.RESULT
        assert result.sender == PRIME_AGENT
        assert result.recipient == USER_SENDER
        assert result.parent_id == "msg_original"
