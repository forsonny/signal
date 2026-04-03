"""LogToolCallsHook -- logs tool calls to JSONL."""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from signalagent.core.models import ToolResult

logger = logging.getLogger(__name__)

class LogToolCallsHook:
    """Logs every tool call to a JSONL file.

    Each entry is a single JSON object on one line containing
    ``timestamp``, ``tool_name``, ``arguments``, ``error``,
    ``duration_ms``, and ``blocked`` fields.  The log file is
    created at ``<log_dir>/tool_calls.jsonl``.
    """

    def __init__(self, log_dir: Path) -> None:
        """Initialise the logging hook.

        Args:
            log_dir: Directory where ``tool_calls.jsonl`` is written.
                Created on first write if it does not exist.
        """
        self._log_dir = log_dir
        self._pending_start: float | None = None
        # NOTE: _pending_start as instance state works because hooks
        # are called sequentially on a single coroutine (no concurrent
        # tool calls in 4b). If Phase 5+ adds concurrency, this needs
        # to change (e.g., pass context through lifecycle, or key by
        # tool_call_id).

    @property
    def name(self) -> str:
        """Unique hook name for logging and diagnostics."""
        return "log_tool_calls"

    async def before_tool_call(self, tool_name: str, arguments: dict, agent: str = "") -> ToolResult | None:
        """Record the call start time. Never blocks.

        Args:
            tool_name: Name of the tool about to be called.
            arguments: Arguments the LLM supplied.
            agent: Name of the calling agent.

        Returns:
            Always None (observe-only).
        """
        self._pending_start = time.monotonic()
        return None  # always allows

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult, blocked: bool, agent: str = "",
    ) -> None:
        """Write a JSONL log entry with timing information.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments the LLM supplied.
            result: The ToolResult produced.
            blocked: True if a before-hook blocked execution.
            agent: Name of the calling agent.
        """
        duration_ms = 0
        if self._pending_start is not None:
            duration_ms = int((time.monotonic() - self._pending_start) * 1000)
            self._pending_start = None

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "arguments": arguments,
            "error": result.error,
            "duration_ms": duration_ms,
            "blocked": blocked,
        }

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._log_dir / "tool_calls.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning("Failed to write tool call log: %s", e)
