"""AuditLogger -- structured JSONL audit trail for policy decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    """A single audit trail entry."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    event_type: str
    agent: str
    detail: dict[str, Any]


class AuditLogger:
    """Appends audit events to a JSONL file.

    Same pattern as LogToolCallsHook (JSONL append) and
    SessionManager (file-based persistence). Pure I/O, no logic.
    """

    def __init__(self, audit_dir: Path) -> None:
        self._audit_dir = audit_dir
        self._warned_agents: set[str] = set()

    def log(self, event: AuditEvent) -> None:
        """Append a single event to audit.jsonl."""
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        path = self._audit_dir / "audit.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def warn_no_policy(self, agent: str) -> None:
        """Log 'no policy configured' warning, deduplicated per agent.

        Tracked in-memory -- resets per process lifetime, not persisted.
        """
        if agent in self._warned_agents:
            return
        self._warned_agents.add(agent)
        self.log(AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="warning",
            agent=agent,
            detail={"message": f"No policy configured for agent '{agent}'"},
        ))
