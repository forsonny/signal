"""Hook protocol -- interface every hook must implement."""
from __future__ import annotations
from typing import Protocol
from signalagent.core.models import ToolResult

class Hook(Protocol):
    """Protocol for tool call hooks. Hooks observe and optionally block
    tool calls. They cannot modify arguments or results."""

    @property
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict,
    ) -> ToolResult | None:
        """Return None to allow, or ToolResult with error to block."""
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None:
        """Observe only. Always fires, including on blocked calls."""
        ...
