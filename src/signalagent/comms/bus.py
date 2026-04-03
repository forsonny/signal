"""MessageBus -- typed message delivery between agents."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from signalagent.core.errors import RoutingError
from signalagent.core.models import Message
from signalagent.core.types import HEARTBEAT_SENDER, USER_SENDER

logger = logging.getLogger(__name__)

_VIRTUAL_SENDERS = frozenset({USER_SENDER, HEARTBEAT_SENDER})

MessageHandler = Callable[[Message], Awaitable[Message | None]]


def generate_message_id() -> str:
    """Generate a unique message ID: ``msg_`` + 8 hex chars.

    Returns:
        A string like ``"msg_a1b2c3d4"``.
    """
    return f"msg_{secrets.token_hex(4)}"


class MessageBus:
    """In-process message bus with talks_to enforcement.

    Agents register handlers and permission sets. Messages are delivered
    synchronously (awaited inline, no queuing). The bus auto-fills id
    and created on send if not already set.

    USER_SENDER is a virtual sender -- allowed without registration.
    Agents with talks_to=None have unrestricted sending permissions.
    """

    def __init__(self) -> None:
        """Initialise an empty message bus with no registered agents."""
        self._permissions: dict[str, set[str] | None] = {}
        self._handlers: dict[str, MessageHandler] = {}
        self._log: list[Message] = []

    def register(
        self,
        agent_name: str,
        handler: MessageHandler,
        talks_to: set[str] | None,
    ) -> None:
        """Register an agent's message handler and talks_to permissions.

        Args:
            agent_name: Unique name for this agent.
            handler: Async callable that processes incoming messages.
            talks_to: Set of agent names this agent can send to.
                       None means unrestricted. set() means can't send to anyone.
        """
        self._handlers[agent_name] = handler
        self._permissions[agent_name] = talks_to

    def unregister(self, agent_name: str) -> None:
        """Remove an agent from the bus."""
        self._handlers.pop(agent_name, None)
        self._permissions.pop(agent_name, None)

    async def send(self, message: Message) -> Message | None:
        """Deliver a message to the recipient's handler.

        Auto-fills message.id and message.created if not already set.
        Logs both the sent message and any response.

        Returns the handler's response Message, or None.

        Raises:
            RoutingError: If sender/recipient validation or talks_to check fails.
        """
        # Auto-fill infrastructure fields
        if not message.id:
            message.id = generate_message_id()
        if message.created is None:
            message.created = datetime.now(timezone.utc)

        sender = message.sender
        recipient = message.recipient

        # Sender validation: must be registered OR be a virtual sender
        if sender not in _VIRTUAL_SENDERS and sender not in self._handlers:
            raise RoutingError(f"Sender '{sender}' is not registered")

        # Recipient validation: must be registered
        if recipient not in self._handlers:
            raise RoutingError(f"Recipient '{recipient}' is not registered")

        # talks_to enforcement: skip for virtual senders and unrestricted agents
        if sender not in _VIRTUAL_SENDERS:
            allowed = self._permissions.get(sender)
            if allowed is not None and recipient not in allowed:
                raise RoutingError(
                    f"'{sender}' talks_to does not include '{recipient}'"
                )

        # Log the sent message
        self._log.append(message)

        # Deliver
        handler = self._handlers[recipient]
        logger.debug("Bus: %s -> %s (%s)", sender, recipient, message.type.value)
        response = await handler(message)

        # Log the response if one was returned
        if response is not None:
            if not response.id:
                response.id = generate_message_id()
            if response.created is None:
                response.created = datetime.now(timezone.utc)
            self._log.append(response)

        return response

    @property
    def log(self) -> list[Message]:
        """Message history. Read-only access for observability."""
        return self._log
