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
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Return None to allow, or ToolResult with error to block."""
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None:
        """Observe only. Always fires, including on blocked calls."""
        ...
