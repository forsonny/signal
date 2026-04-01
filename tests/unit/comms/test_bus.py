"""Unit tests for MessageBus -- no agents, no AI. Dummy async handlers only."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from signalagent.comms.bus import MessageBus, generate_message_id
from signalagent.core.errors import RoutingError
from signalagent.core.models import Message
from signalagent.core.types import (
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)


def _make_message(
    sender: str = "agent-a",
    recipient: str = "agent-b",
    content: str = "hello",
    msg_type: MessageType = MessageType.TASK,
) -> Message:
    return Message(
        type=msg_type,
        sender=sender,
        recipient=recipient,
        content=content,
    )


class TestGenerateMessageId:
    def test_starts_with_prefix(self):
        mid = generate_message_id()
        assert mid.startswith("msg_")

    def test_correct_length(self):
        mid = generate_message_id()
        assert len(mid) == 12

    def test_unique(self):
        ids = {generate_message_id() for _ in range(100)}
        assert len(ids) == 100


class TestRegisterUnregister:
    def test_register_agent(self):
        bus = MessageBus()
        handler = AsyncMock(return_value=None)
        bus.register("agent-a", handler, talks_to={"agent-b"})

    @pytest.mark.asyncio
    async def test_unregister_agent(self):
        bus = MessageBus()
        handler = AsyncMock(return_value=None)
        bus.register("agent-a", handler, talks_to=None)
        bus.unregister("agent-a")
        msg = _make_message(sender=USER_SENDER, recipient="agent-a")
        with pytest.raises(RoutingError, match="not registered"):
            await bus.send(msg)


class TestSend:
    @pytest.mark.asyncio
    async def test_delivers_message_to_handler(self):
        bus = MessageBus()
        handler_b = AsyncMock(return_value=None)
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", handler_b, talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        await bus.send(msg)

        handler_b.assert_called_once()
        delivered = handler_b.call_args[0][0]
        assert delivered.content == "hello"

    @pytest.mark.asyncio
    async def test_returns_handler_response(self):
        bus = MessageBus()
        response_msg = Message(
            type=MessageType.RESULT,
            sender="agent-b",
            recipient="agent-a",
            content="done",
        )
        handler_b = AsyncMock(return_value=response_msg)
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", handler_b, talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "done"

    @pytest.mark.asyncio
    async def test_auto_fills_id_and_created(self):
        bus = MessageBus()
        handler_b = AsyncMock(return_value=None)
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", handler_b, talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        assert msg.id == ""
        assert msg.created is None

        await bus.send(msg)

        assert msg.id.startswith("msg_")
        assert msg.created is not None

    @pytest.mark.asyncio
    async def test_preserves_existing_id_and_created(self):
        bus = MessageBus()
        handler_b = AsyncMock(return_value=None)
        bus.register("agent-a", AsyncMock(), talks_to=None)
        bus.register("agent-b", handler_b, talks_to=None)

        now = datetime.now(timezone.utc)
        msg = Message(
            id="msg_custom01",
            type=MessageType.TASK,
            sender="agent-a",
            recipient="agent-b",
            content="hello",
            created=now,
        )
        await bus.send(msg)

        assert msg.id == "msg_custom01"
        assert msg.created == now

    @pytest.mark.asyncio
    async def test_user_sender_allowed_without_registration(self):
        bus = MessageBus()
        handler_prime = AsyncMock(return_value=None)
        bus.register(PRIME_AGENT, handler_prime, talks_to=None)

        msg = _make_message(sender=USER_SENDER, recipient=PRIME_AGENT)
        await bus.send(msg)

        handler_prime.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_for_fire_and_forget(self):
        bus = MessageBus()
        handler_b = AsyncMock(return_value=None)
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", handler_b, talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        result = await bus.send(msg)

        assert result is None


class TestTalksToEnforcement:
    @pytest.mark.asyncio
    async def test_rejects_unauthorized_sender(self):
        bus = MessageBus()
        bus.register("agent-a", AsyncMock(), talks_to={"agent-c"})
        bus.register("agent-b", AsyncMock(), talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        with pytest.raises(RoutingError, match="talks_to"):
            await bus.send(msg)

    @pytest.mark.asyncio
    async def test_empty_talks_to_blocks_all(self):
        bus = MessageBus()
        bus.register("agent-a", AsyncMock(), talks_to=set())
        bus.register("agent-b", AsyncMock(), talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        with pytest.raises(RoutingError, match="talks_to"):
            await bus.send(msg)

    @pytest.mark.asyncio
    async def test_none_talks_to_allows_all(self):
        bus = MessageBus()
        handler_b = AsyncMock(return_value=None)
        bus.register("agent-a", AsyncMock(), talks_to=None)
        bus.register("agent-b", handler_b, talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        await bus.send(msg)

        handler_b.assert_called_once()

    @pytest.mark.asyncio
    async def test_unrestricted_agent_bypasses_talks_to(self):
        """Prime bypasses talks_to via talks_to=None registration, not name check."""
        bus = MessageBus()
        handler_micro = AsyncMock(return_value=None)
        bus.register(PRIME_AGENT, AsyncMock(), talks_to=None)  # None = unrestricted
        bus.register("micro-a", handler_micro, talks_to=set())

        msg = _make_message(sender=PRIME_AGENT, recipient="micro-a")
        await bus.send(msg)

        handler_micro.assert_called_once()


class TestSendErrors:
    @pytest.mark.asyncio
    async def test_unregistered_sender_rejected(self):
        bus = MessageBus()
        bus.register("agent-b", AsyncMock(), talks_to=None)

        msg = _make_message(sender="unknown", recipient="agent-b")
        with pytest.raises(RoutingError, match="not registered"):
            await bus.send(msg)

    @pytest.mark.asyncio
    async def test_unregistered_recipient_rejected(self):
        bus = MessageBus()
        bus.register("agent-a", AsyncMock(), talks_to=None)

        msg = _make_message(sender="agent-a", recipient="unknown")
        with pytest.raises(RoutingError, match="not registered"):
            await bus.send(msg)


class TestLog:
    @pytest.mark.asyncio
    async def test_logs_sent_messages(self):
        bus = MessageBus()
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", AsyncMock(return_value=None), talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        await bus.send(msg)

        assert len(bus.log) >= 1
        assert bus.log[0].content == "hello"

    @pytest.mark.asyncio
    async def test_logs_response_messages(self):
        bus = MessageBus()
        response_msg = Message(
            type=MessageType.RESULT,
            sender="agent-b",
            recipient="agent-a",
            content="done",
        )
        bus.register("agent-a", AsyncMock(), talks_to={"agent-b"})
        bus.register("agent-b", AsyncMock(return_value=response_msg), talks_to=None)

        msg = _make_message(sender="agent-a", recipient="agent-b")
        await bus.send(msg)

        assert len(bus.log) == 2
        assert bus.log[1].content == "done"
