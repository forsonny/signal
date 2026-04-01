"""Unit tests for PrimeAgent -- mock AILayer, real bus, stub micro-agents."""

import pytest
from unittest.mock import AsyncMock, patch

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AIResponse
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Memory, Message
from signalagent.core.types import (
    AgentType,
    MemoryType,
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)

from datetime import datetime, timezone


def _make_ai_response(content: str) -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


def _make_memory(content="Prime context", tags=None):
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001", agent="prime", type=MemoryType.LEARNING,
        tags=tags or ["general"], content=content, confidence=0.8, version=1,
        created=now, updated=now, accessed=now, access_count=0,
    )


def _stub_count_tokens(text: str, model: str) -> int:
    return len(text) // 4


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
    memory_reader=None,
    model: str = "",
) -> PrimeAgent:
    prime = PrimeAgent(
        identity=identity, ai=mock_ai, host=host, bus=bus,
        memory_reader=memory_reader, model=model,
    )
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


class TestMemoryIntegration:
    @pytest.mark.asyncio
    async def test_handle_directly_enriches_prompt_with_memories(self, host, bus):
        """When memory_reader is provided, direct handling includes memories."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            await bus.send(msg)

        mock_reader.search.assert_called_once()
        call_kwargs = mock_reader.search.call_args.kwargs
        assert call_kwargs["agent"] == "prime"

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert "## Context" in system_content
        assert "Prime context" in system_content

    @pytest.mark.asyncio
    async def test_routing_does_not_use_memories(self, host, bus):
        """Routing prompt should NOT include memories."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="review code",
        )
        await bus.send(msg)

        # Routing succeeded (AI returned "code-review"), so Prime dispatched
        # to the micro-agent and never entered _handle_directly() where
        # memory search happens. assert_not_called() is valid because this
        # test verifies routing doesn't trigger memory retrieval -- NOT that
        # Prime never uses memories (see test_handle_directly_enriches_prompt).
        mock_reader.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_memory_reader_uses_identity_only(self, host, bus):
        """Without memory_reader, direct handling uses raw identity."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))

        _register_prime(host, bus, mock_ai)

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        await bus.send(msg)

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert system_content == "You are a test prime."
        assert "## Context" not in system_content

    @pytest.mark.asyncio
    async def test_memory_search_failure_proceeds_without_context(self, host, bus):
        """If memory search fails, Prime proceeds with identity-only prompt."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(side_effect=Exception("DB error"))

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "response"
        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert "## Context" not in system_content
