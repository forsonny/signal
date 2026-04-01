"""Built-in hook loading."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalagent.hooks.protocol import Hook

def load_builtin_hook(name: str, instance_dir: Path) -> "Hook | None":
    if name == "log_tool_calls":
        from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook
        return LogToolCallsHook(log_dir=instance_dir / "logs")
    return None
