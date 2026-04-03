"""Built-in tool loading."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalagent.tools.protocol import Tool


def load_builtin_tool(name: str, instance_dir: Path) -> "Tool | None":
    """Load a built-in tool by name using deferred imports.

    Args:
        name: Registered tool name (e.g. ``"file_system"``).
        instance_dir: Root directory the tool is scoped to.

    Returns:
        An instantiated Tool, or None if *name* is not a known built-in.
    """
    if name == "file_system":
        from signalagent.tools.builtins.file_system import FileSystemTool
        return FileSystemTool(root=instance_dir)
    return None
