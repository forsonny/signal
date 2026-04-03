"""FileSystemTool -- scoped read/write/list operations within an instance directory."""
from __future__ import annotations

from pathlib import Path

from signalagent.core.models import ToolResult

_DEFAULT_MAX_READ_BYTES = 1 * 1024 * 1024  # 1 MB


class FileSystemTool:
    """Read, write, and list files scoped to a root directory."""

    def __init__(self, root: Path, max_read_bytes: int = _DEFAULT_MAX_READ_BYTES) -> None:
        """Initialise a file-system tool scoped to *root*.

        Args:
            root: Workspace root directory. All paths are resolved
                relative to this directory; escapes are rejected.
            max_read_bytes: Maximum bytes returned by a read before
                the output is truncated. Defaults to 1 MB.
        """
        self._root = root.resolve()
        self._max_read_bytes = max_read_bytes

    @property
    def name(self) -> str:
        """Unique tool name used for LLM function calling."""
        return "file_system"

    @property
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        return "Read, write, and list files within the workspace."

    @property
    def parameters(self) -> dict:
        """JSON Schema for the tool's arguments."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "list"],
                    "description": "The file operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (write operation only).",
                },
            },
            "required": ["operation", "path"],
        }

    def _resolve_safe(self, path_str: str) -> Path | None:
        """Resolve path relative to root; return None if outside root."""
        # Reject absolute paths outright
        candidate = Path(path_str)
        if candidate.is_absolute():
            return None

        resolved = (self._root / path_str).resolve()

        # String-based prefix check handles Windows drive letters correctly
        root_str = str(self._root)
        resolved_str = str(resolved)

        # Ensure the resolved path is inside the root (account for exact match)
        if resolved_str == root_str or resolved_str.startswith(root_str + "\\") or resolved_str.startswith(root_str + "/"):
            return resolved
        return None

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a file-system operation.

        Args:
            **kwargs: Must include ``operation`` (read/write/list) and
                ``path``. Write operations also require ``content``.

        Returns:
            ToolResult with the file content, confirmation, or error.
        """
        operation = kwargs.get("operation", "")
        path_str = kwargs.get("path", "")

        if operation == "read":
            return await self._read(path_str)
        elif operation == "write":
            content = kwargs.get("content", "")
            return await self._write(path_str, content)
        elif operation == "list":
            return await self._list(path_str)
        else:
            return ToolResult(output="", error=f"Unknown operation: '{operation}'")

    async def _read(self, path_str: str) -> ToolResult:
        """Read a file, truncating if it exceeds *max_read_bytes*."""
        resolved = self._resolve_safe(path_str)
        if resolved is None:
            return ToolResult(output="", error="Path outside workspace")

        if not resolved.exists():
            return ToolResult(output="", error=f"File not found: {path_str}")

        if not resolved.is_file():
            return ToolResult(output="", error=f"Not a file: {path_str}")

        file_size = resolved.stat().st_size
        cap = self._max_read_bytes

        raw_bytes = resolved.read_bytes()
        if file_size > cap:
            truncated = raw_bytes[:cap].decode("utf-8", errors="replace")
            cap_mb = round(cap / (1024 * 1024), 2)
            size_mb = round(file_size / (1024 * 1024), 2)
            note = f"\n[truncated at {cap_mb}MB, file is {size_mb}MB]"
            return ToolResult(output=truncated + note)

        text = raw_bytes.decode("utf-8", errors="replace")
        return ToolResult(output=text)

    async def _write(self, path_str: str, content: str) -> ToolResult:
        """Write *content* to a file, creating parent directories as needed."""
        resolved = self._resolve_safe(path_str)
        if resolved is None:
            return ToolResult(output="", error="Path outside workspace")

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ToolResult(output=f"Written: {path_str}")

    async def _list(self, path_str: str) -> ToolResult:
        """List entries in a directory, directories first."""
        resolved = self._resolve_safe(path_str)
        if resolved is None:
            return ToolResult(output="", error="Path outside workspace")

        if not resolved.exists():
            return ToolResult(output="", error=f"Directory not found: {path_str}")

        if not resolved.is_dir():
            return ToolResult(output="", error=f"Not a directory: {path_str}")

        entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(entry.name + "/")
            else:
                lines.append(entry.name)

        return ToolResult(output="\n".join(lines))
