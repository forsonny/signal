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
        """Initialise the spawn tool.

        Args:
            run_sub: Async callable ``(system_prompt, user_msg) -> str``
                that executes a sub-agent loop and returns its final text.
            parent_name: Name of the parent agent, used to derive
                unique sub-agent identifiers.
        """
        self._run_sub = run_sub
        self._parent_name = parent_name
        self._counter = 0
        # NOTE: _counter as instance state works because tool calls
        # are sequential on a single coroutine (no concurrent spawns
        # in 4c).

    @property
    def name(self) -> str:
        """Unique tool name used for LLM function calling."""
        return "spawn_sub_agent"

    @property
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        return "Spawn an ephemeral sub-agent to handle a subtask."

    @property
    def parameters(self) -> dict:
        """JSON Schema for the tool's arguments."""
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
        """Spawn a sub-agent for the requested task.

        Args:
            **kwargs: Must include ``task`` (the objective) and
                ``skill`` (the sub-agent's area of expertise).

        Returns:
            ToolResult containing the sub-agent's final output.
        """
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
