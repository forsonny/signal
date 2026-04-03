"""Hook protocol -- interface every hook must implement."""
from __future__ import annotations
from typing import Protocol
from signalagent.core.models import ToolResult


class Hook(Protocol):
    """Protocol for tool call hooks.

    Hooks observe and optionally block tool calls. They cannot modify
    arguments or results.

    Failure mode: hooks default to fail-open (crash = log + continue).
    Safety-critical hooks (e.g., PolicyHook) set a ``fail_closed``
    property to ``True`` so a crash blocks the call rather than
    allowing it through.  The HookExecutor checks for this via
    ``getattr(hook, 'fail_closed', False)``.
    """

    @property
    def name(self) -> str:
        """Unique hook name for logging and diagnostics."""
        ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Inspect or block a tool call before execution.

        Args:
            tool_name: Name of the tool about to be called.
            arguments: Arguments the LLM supplied.
            agent: Name of the calling agent (empty for the root agent).

        Returns:
            None to allow the call, or a ToolResult (with error) to block it.
        """
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None:
        """Observe a completed (or blocked) tool call.

        Always fires, including when a before-hook blocked the call.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments the LLM supplied.
            result: The ToolResult produced (or the blocking result).
            blocked: True if a before-hook blocked execution.
            agent: Name of the calling agent.
        """
        ...
