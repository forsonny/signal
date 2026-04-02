"""MicroAgent -- skill-based specialist agent."""
from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import (
    MemoryReaderProtocol,
    RunnerProtocol,
    WorktreeProxyProtocol,
)
from signalagent.core.types import AgentType, MessageType
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT

logger = logging.getLogger(__name__)


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.
    Delegates all LLM interaction to an injected RunnerProtocol."""

    def __init__(
        self,
        config: MicroAgentConfig,
        runner: RunnerProtocol,
        memory_reader: MemoryReaderProtocol | None = None,
        model: str = "",
        worktree_proxy: WorktreeProxyProtocol | None = None,
    ) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._memory_reader = memory_reader
        self._model = model
        self._worktree_proxy = worktree_proxy

    @property
    def skill(self) -> str:
        return self._config.skill

    def _build_identity(self) -> str:
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        if self._worktree_proxy is not None:
            async with self._worktree_proxy.task_lock():
                return await self._handle_inner(message)
        return await self._handle_inner(message)

    async def _handle_inner(self, message: Message) -> Message | None:
        memories = []
        if self._memory_reader:
            try:
                memories = await self._memory_reader.search(
                    agent=self._config.name, limit=DEFAULT_MEMORY_LIMIT,
                )
            except Exception:
                logger.warning("Memory retrieval failed, proceeding without context")

        if memories and self._model:
            system_prompt = build_system_prompt(
                identity=self._build_identity(),
                memories=memories,
                model=self._model,
            )
        elif memories:
            logger.warning("Memories retrieved but no model set; skipping context injection")
            system_prompt = self._build_identity()
        else:
            system_prompt = self._build_identity()

        error: Exception | None = None
        try:
            result = await self._runner.run(
                system_prompt=system_prompt,
                user_content=message.content,
            )
            content = result.content
        except Exception as exc:
            error = exc
            content = f"Task failed: {exc}"

        # Check for worktree changes regardless of success/failure
        wt_review = ""
        if self._worktree_proxy is not None:
            wt_result = self._worktree_proxy.take_result()
            if wt_result is not None:
                files_str = "\n".join(f"- {f}" for f in wt_result.changed_files)
                wt_review = (
                    f"\n\nChanges ready for review:\n{files_str}\n\n"
                    f"Run: signal worktree merge {wt_result.id}\n"
                    f"Or:  signal worktree discard {wt_result.id}"
                )

        # Error with no worktree state: propagate as before
        if error is not None and not wt_review:
            raise error

        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=content + wt_review,
            parent_id=message.id,
        )
