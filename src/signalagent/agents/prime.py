"""PrimeAgent -- LLM-based routing with direct handling fallback."""

from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import (
    AgentType,
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)
from signalagent.core.protocols import AILayerProtocol

logger = logging.getLogger(__name__)


class PrimeAgent(BaseAgent):
    """Prime agent: routes tasks to micro-agents or handles directly.

    Routing uses an LLM call to decide which micro-agent should handle
    the user's message. If no match, if the LLM returns garbage, or if
    the routing call itself fails, Prime handles the request directly
    using its own identity prompt.
    """

    def __init__(
        self,
        identity: str,
        ai: AILayerProtocol,
        host: AgentHost,
        bus: MessageBus,
    ) -> None:
        super().__init__(name=PRIME_AGENT, agent_type=AgentType.PRIME)
        self._identity = identity
        self._ai = ai
        self._host = host
        self._bus = bus

    async def _handle(self, message: Message) -> Message | None:
        """Route to micro-agent or handle directly."""
        micro_agents = self._host.list_micro_agents()

        if not micro_agents:
            content = await self._handle_directly(message.content)
        else:
            target = await self._route(message.content, micro_agents)
            if target is not None:
                # Dispatch to micro-agent via bus
                task_msg = Message(
                    type=MessageType.TASK,
                    sender=PRIME_AGENT,
                    recipient=target,
                    content=message.content,
                    parent_id=message.id,
                )
                micro_response = await self._bus.send(task_msg)
                content = micro_response.content if micro_response else ""
            else:
                content = await self._handle_directly(message.content)

        return Message(
            type=MessageType.RESULT,
            sender=PRIME_AGENT,
            recipient=message.sender,
            content=content,
            parent_id=message.id,
        )

    async def _route(
        self,
        user_content: str,
        micro_agents: list[BaseAgent],
    ) -> str | None:
        """LLM routing call. Returns micro-agent name or None.

        If the routing call fails, catches the exception and returns None.
        Routing failure must never crash Prime.
        """
        agent_list = "\n".join(
            f"- {a.name}: {a.skill}"
            for a in micro_agents
        )
        n = len(micro_agents)
        routing_prompt = (
            "You are a routing agent. Given the user's message and the "
            "available specialist agents below, decide which agent should "
            "handle this task.\n\n"
            f"Available agents ({n}):\n"
            f"{agent_list}\n\n"
            "If none of the agents are a good fit, respond with: NONE\n\n"
            "Otherwise respond with exactly the agent name, nothing else.\n\n"
            f"User message: {user_content}"
        )

        try:
            response = await self._ai.complete(
                messages=[{"role": "user", "content": routing_prompt}],
            )
        except Exception:
            logger.warning("Routing LLM call failed, falling back to direct handling")
            return None

        choice = response.content.strip().lower()

        if choice == "none" or not choice:
            return None

        # Case-insensitive match against registered micro-agent names
        name_map = {a.name.lower(): a.name for a in micro_agents}
        return name_map.get(choice)

    async def _handle_directly(self, user_content: str) -> str:
        """Execute using Prime's own identity prompt. Fallback path."""
        response = await self._ai.complete(
            messages=[
                {"role": "system", "content": self._identity},
                {"role": "user", "content": user_content},
            ],
        )
        return response.content
