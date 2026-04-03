"""Built-in hook loading."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalagent.hooks.protocol import Hook


def load_builtin_hook(name: str, instance_dir: Path) -> "Hook | None":
    """Load a built-in hook by name using deferred imports.

    Args:
        name: Registered hook name (e.g. ``"log_tool_calls"``).
        instance_dir: Agent instance directory; used to derive
            log paths and other hook-specific configuration.

    Returns:
        An instantiated Hook, or None if *name* is not a known built-in.
    """
    if name == "log_tool_calls":
        from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook
        return LogToolCallsHook(log_dir=instance_dir / "logs")
    return None
