"""Protocol definitions for dependency injection across packages.

All protocol types that agents and tools depend on live here. Concrete
implementations live in their respective packages (ai/, runtime/).
This keeps the dependency graph clean: core/ depends on nothing,
everything else can depend on core/.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class AILayerProtocol(Protocol):
    """Protocol for the AI layer so agents don't depend on concrete class."""

    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: list[dict] | None = None,
    ) -> Any: ...


@runtime_checkable
class RunnerProtocol(Protocol):
    """Protocol for the agentic loop runner.
    Agents depend on this protocol, not the concrete AgenticRunner."""
    async def run(
        self,
        system_prompt: str,
        user_content: str,
    ) -> Any: ...


@runtime_checkable
class ToolExecutor(Protocol):
    """Protocol for tool execution callable.
    The runner calls this to execute tools. In 4a it wraps
    registry.get(name).execute(**args). In 4b it gets replaced
    with a hook-aware version."""
    async def __call__(
        self,
        tool_name: str,
        arguments: dict,
    ) -> Any: ...
