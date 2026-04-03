"""Tool protocol -- interface every tool must implement."""
from __future__ import annotations
from typing import Protocol
from signalagent.core.models import ToolResult


class Tool(Protocol):
    """Interface for Signal tools.

    Every tool exposes a name, description, JSON Schema parameters,
    and an async execute method. The registry generates LiteLLM-format
    schemas from these properties.
    """

    @property
    def name(self) -> str:
        """Unique tool name used for LLM function calling."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        ...

    @property
    def parameters(self) -> dict:
        """JSON Schema for the tool's arguments."""
        ...

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific arguments matching the parameters schema.

        Returns:
            ToolResult with output text or error.
        """
        ...
