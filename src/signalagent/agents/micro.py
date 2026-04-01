"""MicroAgent -- skill-based specialist agent."""
from __future__ import annotations

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import RunnerProtocol
from signalagent.core.types import AgentType, MessageType


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.
    Delegates all LLM interaction to an injected RunnerProtocol."""

    def __init__(self, config: MicroAgentConfig, runner: RunnerProtocol) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._system_prompt = self._build_system_prompt()

    @property
    def skill(self) -> str:
        return self._config.skill

    def _build_system_prompt(self) -> str:
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        result = await self._runner.run(
            system_prompt=self._system_prompt,
            user_content=message.content,
        )
        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=result.content,
            parent_id=message.id,
        )
