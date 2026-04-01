"""MicroAgent -- skill-based specialist agent."""

from __future__ import annotations

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import AgentType, MessageType
from signalagent.core.protocols import AILayerProtocol


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.

    The system prompt is generated from a template plus the config's skill
    field. Profile authors who want full control write a detailed skill
    field; the template ensures minimum viable context.
    """

    def __init__(self, config: MicroAgentConfig, ai: AILayerProtocol) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._ai = ai
        self._system_prompt = self._build_system_prompt()

    @property
    def skill(self) -> str:
        """Agent's skill description from config."""
        return self._config.skill

    def _build_system_prompt(self) -> str:
        """Generate system prompt from template + config."""
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        """Execute task using own AI call with skill-based system prompt."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": message.content},
        ]

        response = await self._ai.complete(messages=messages)

        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=response.content,
            parent_id=message.id,
        )
