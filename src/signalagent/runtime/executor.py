"""Executor -- sends user messages to Prime via the MessageBus."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from signalagent.comms.bus import MessageBus
    from signalagent.sessions.manager import SessionManager

from signalagent.core.models import Message, Turn
from signalagent.core.protocols import AILayerProtocol
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT

logger = logging.getLogger(__name__)

__all__ = ["AILayerProtocol", "ExecutorResult", "Executor"]


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

    def __init__(
        self,
        bus: MessageBus,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._bus = bus
        self._session_manager = session_manager

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
    ) -> ExecutorResult:
        """Send user message to Prime via bus, return result.

        Args:
            user_message: The user's input text.
            session_id: Optional session ID for multi-turn persistence.
                If provided, loads conversation history and appends
                turns on success.

        Returns:
            ExecutorResult with content or error. Never raises.
        """
        history: list[dict[str, Any]] = []
        if session_id and self._session_manager:
            turns = self._session_manager.load(session_id)
            history = [{"role": t.role, "content": t.content} for t in turns]

        message = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content=user_message,
            history=history,
        )

        try:
            response = await self._bus.send(message)
            if response is None:
                return ExecutorResult(
                    content="",
                    error="No response from agent",
                )

            if session_id and self._session_manager:
                now = datetime.now(timezone.utc)
                self._session_manager.append(
                    session_id, Turn(role="user", content=user_message, timestamp=now),
                )
                self._session_manager.append(
                    session_id, Turn(role="assistant", content=response.content, timestamp=now),
                )

            return ExecutorResult(content=response.content)
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(
                content="",
                error=str(e),
                error_type=type(e).__name__,
            )
