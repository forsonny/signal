"""AgentHost -- agent registry backed by the MessageBus."""

from __future__ import annotations

from signalagent.agents.base import BaseAgent
from signalagent.comms.bus import MessageBus
from signalagent.core.types import AgentStatus, AgentType


class AgentHost:
    """Registry that tracks agents and wires them to the bus.

    Supports runtime registration -- agents don't have to come from
    profiles. Dynamic agent creation by Prime is deferred to post-Phase 9.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._agents: dict[str, BaseAgent] = {}

    def register(
        self,
        agent: BaseAgent,
        talks_to: set[str] | None = None,
    ) -> None:
        """Register agent with host and bus. Sets status to ACTIVE."""
        self._agents[agent.name] = agent
        agent.status = AgentStatus.ACTIVE
        self._bus.register(agent.name, agent.handle, talks_to)

    def get(self, name: str) -> BaseAgent | None:
        """Look up a registered agent by name."""
        return self._agents.get(name)

    def list_micro_agents(self) -> list[BaseAgent]:
        """Return all registered specialist agents. Used by Prime for routing."""
        return [
            a for a in self._agents.values()
            if a.agent_type in (AgentType.MICRO, AgentType.MEMORY_KEEPER)
        ]

    def unregister(self, name: str) -> None:
        """Remove agent from host and bus. Sets status to ARCHIVED."""
        agent = self._agents.pop(name, None)
        if agent is not None:
            agent.status = AgentStatus.ARCHIVED
            self._bus.unregister(name)
