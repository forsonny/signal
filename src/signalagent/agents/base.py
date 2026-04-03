"""BaseAgent -- template method for status management.

Provides the foundational agent contract: name, type, status lifecycle,
and the handle/_handle template-method pattern.
"""

from __future__ import annotations

from signalagent.core.models import Message
from signalagent.core.types import AgentStatus, AgentType


class BaseAgent:
    """Base class for all agents.

    Subclasses override _handle(), never handle(). The template method
    in handle() manages BUSY/IDLE status transitions automatically.
    """

    def __init__(self, name: str, agent_type: AgentType) -> None:
        """Initialise a new agent.

        Args:
            name: Unique agent name used for bus registration and routing.
            agent_type: The kind of agent (PRIME, MICRO, SUB, MEMORY_KEEPER).
        """
        self.name = name
        self.agent_type = agent_type
        self.status = AgentStatus.CREATED

    @property
    def skill(self) -> str:
        """Agent's skill description. Override in subclasses."""
        return ""

    async def handle(self, message: Message) -> Message | None:
        """Template method. Sets BUSY, delegates to _handle, sets IDLE.

        Args:
            message: Incoming message from the bus.

        Returns:
            Response message, or None if no reply is needed.
        """
        self.status = AgentStatus.BUSY
        try:
            return await self._handle(message)
        finally:
            self.status = AgentStatus.IDLE

    async def _handle(self, message: Message) -> Message | None:
        """Process a message. Override in subclasses."""
        raise NotImplementedError
