"""SpawnSubAgentTool -- spawns ephemeral sub-agents for task delegation."""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from signalagent.core.models import ToolResult


class SpawnSubAgentTool:
    """Spawns an ephemeral sub-agent to handle a subtask.

    The sub-agent gets its own agentic loop (via the injected run_sub
    callable) with the parent's tools minus this spawn tool. The result
    is returned as a normal ToolResult.

    Implements the Tool protocol. The runner, hooks, and registry
    don't know this tool is special.
    """

    def __init__(
        self,
        run_sub: Callable[[str, str], Awaitable[str]],
        parent_name: str,
    ) -> None:
        self._run_sub = run_sub
        self._parent_name = parent_name
        self._counter = 0
        # NOTE: _counter as instance state works because tool calls
        # are sequential on a single coroutine (no concurrent spawns
        # in 4c).

    @property
    def name(self) -> str:
        return "spawn_sub_agent"

    @property
    def description(self) -> str:
        return "Spawn an ephemeral sub-agent to handle a subtask."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the sub-agent to complete.",
                },
                "skill": {
                    "type": "string",
                    "description": "The sub-agent's area of expertise.",
                },
            },
            "required": ["task", "skill"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        task = kwargs.get("task", "")
        skill = kwargs.get("skill", "")

        self._counter += 1
        sub_name = f"sub_{self._parent_name}_{self._counter}"

        system_prompt = (
            f"You are {sub_name}, an ephemeral sub-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {skill}\n\n"
            "Complete the task and return your results."
        )

        result_text = await self._run_sub(system_prompt, task)
        return ToolResult(output=result_text)
