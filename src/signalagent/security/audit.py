"""AuditLogger -- structured JSONL audit trail for policy decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEvent(BaseModel):
    """A single audit trail entry.

    Attributes:
        timestamp: ISO-8601 UTC timestamp of the event.
        event_type: Category such as ``"policy_denial"``, ``"tool_call"``,
            or ``"warning"``.
        agent: Name of the agent associated with the event.
        detail: Arbitrary key-value payload with event-specific data.
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(description="ISO-8601 UTC timestamp of the event.")
    event_type: str = Field(description="Category such as 'policy_denial', 'tool_call', or 'warning'.")
    agent: str = Field(description="Name of the agent associated with the event.")
    detail: dict[str, Any] = Field(description="Arbitrary key-value payload with event-specific data.")


class AuditLogger:
    """Appends audit events to a JSONL file.

    Same pattern as LogToolCallsHook (JSONL append) and
    SessionManager (file-based persistence). Pure I/O, no logic.
    """

    def __init__(self, audit_dir: Path) -> None:
        """Create an audit logger that writes to *audit_dir*/``audit.jsonl``.

        Args:
            audit_dir: Directory where the JSONL audit file is stored.
                Created on first write if it does not exist.
        """
        self._audit_dir = audit_dir
        self._warned_agents: set[str] = set()

    def log(self, event: AuditEvent) -> None:
        """Append a single event to ``audit.jsonl``.

        Args:
            event: The audit event to persist.
        """
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        path = self._audit_dir / "audit.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def warn_no_policy(self, agent: str) -> None:
        """Log a ``"no policy configured"`` warning, deduplicated per agent.

        Tracked in-memory -- resets per process lifetime, not persisted.

        Args:
            agent: Name of the agent that lacks a policy entry.
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
