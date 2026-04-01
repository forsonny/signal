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
