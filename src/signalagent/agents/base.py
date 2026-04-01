"""BaseAgent -- template method for status management."""

from __future__ import annotations

from signalagent.core.models import Message
from signalagent.core.types import AgentStatus, AgentType


class BaseAgent:
    """Base class for all agents.

    Subclasses override _handle(), never handle(). The template method
    in handle() manages BUSY/IDLE status transitions automatically.
    """

    def __init__(self, name: str, agent_type: AgentType) -> None:
        self.name = name
        self.agent_type = agent_type
        self.status = AgentStatus.CREATED

    @property
    def skill(self) -> str:
        """Agent's skill description. Override in subclasses."""
        return ""

    async def handle(self, message: Message) -> Message | None:
        """Template method. Sets BUSY, delegates to _handle, sets IDLE."""
        self.status = AgentStatus.BUSY
        try:
            return await self._handle(message)
        finally:
            self.status = AgentStatus.IDLE

    async def _handle(self, message: Message) -> Message | None:
        """Process a message. Override in subclasses."""
        raise NotImplementedError
