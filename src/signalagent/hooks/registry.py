"""HookRegistry -- storage layer for active hooks."""
from __future__ import annotations
from signalagent.hooks.protocol import Hook

class HookRegistry:
    """Stores hooks and returns them in registration order."""

    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def get_all(self) -> list[Hook]:
        return list(self._hooks)
