"""Executor -- sends user messages to Prime via the MessageBus."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from signalagent.comms.bus import MessageBus

from signalagent.core.models import Message
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT

logger = logging.getLogger(__name__)


@runtime_checkable
class AILayerProtocol(Protocol):
    """Protocol for the AI layer so agents don't depend on concrete class."""

    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> Any: ...


@dataclass
class ExecutorResult:
    """Result of an executor run."""

    content: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class Executor:
    """Sends user messages to Prime via the MessageBus.

    Error boundary: exceptions from the bus/agent chain are caught,
    logged, and returned as an ExecutorResult with error set.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def run(self, user_message: str) -> ExecutorResult:
        """Send user message to Prime via bus, return result.

        Args:
            user_message: The user's input text.

        Returns:
            ExecutorResult with content or error. Never raises.
        """
        message = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content=user_message,
        )

        try:
            response = await self._bus.send(message)
            if response is None:
                return ExecutorResult(
                    content="",
                    error="No response from agent",
                )
            return ExecutorResult(content=response.content)
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(
                content="",
                error=str(e),
                error_type=type(e).__name__,
            )
