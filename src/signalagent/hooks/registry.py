"""HookRegistry -- storage layer for active hooks."""
from __future__ import annotations
from signalagent.hooks.protocol import Hook


class HookRegistry:
    """Stores hooks and returns them in registration order.

    The executor iterates hooks in the order they were registered,
    so ordering matters for before-hooks that may block.
    """

    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        """Append a hook to the registry.

        Args:
            hook: Any object satisfying the Hook protocol.
        """
        self._hooks.append(hook)

    def get_all(self) -> list[Hook]:
        """Return a snapshot of all registered hooks.

        Returns:
            A new list containing hooks in registration order.
        """
        return list(self._hooks)
