"""SessionManager -- JSONL-based conversation session persistence."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.models import Turn, SessionSummary

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """Generate a unique session ID: ses_ + 8 hex chars."""
    return f"ses_{secrets.token_hex(4)}"


class SessionManager:
    """Manages session files in JSONL format.

    Each session is a single file: {sessions_dir}/{session_id}.jsonl
    One JSON line per Turn. Append-only writes, sequential reads.
    Sync I/O -- file operations are fast, no async needed.
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def create(self) -> str:
        """Create a new empty session. Returns the session ID."""
        session_id = generate_session_id()
        path = self._sessions_dir / f"{session_id}.jsonl"
        path.touch()
        return session_id

    def append(self, session_id: str, turn: Turn) -> None:
        """Append a turn to the session's JSONL file."""
        path = self._sessions_dir / f"{session_id}.jsonl"
        line = turn.model_dump_json()
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load(self, session_id: str) -> list[Turn]:
        """Load all turns from a session. Returns empty list if not found."""
        path = self._sessions_dir / f"{session_id}.jsonl"
        if not path.exists():
            return []
        turns: list[Turn] = []
        for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                turns.append(Turn.model_validate_json(line))
            except Exception:
                logger.warning("Corrupt line %d in session %s, skipping", line_num, session_id)
        return turns

    def exists(self, session_id: str) -> bool:
        """Check if a session file exists."""
        return (self._sessions_dir / f"{session_id}.jsonl").exists()

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        """List recent sessions sorted by modification time (newest first)."""
        files = sorted(
            self._sessions_dir.glob("ses_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        summaries: list[SessionSummary] = []
        for f in files:
            session_id = f.stem
            lines = f.read_text(encoding="utf-8").splitlines()
            valid_lines = [l for l in lines if l.strip()]
            turn_count = len(valid_lines)
            preview = ""
            created = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if valid_lines:
                try:
                    first_turn = Turn.model_validate_json(valid_lines[0])
                    preview = first_turn.content[:80]
                    created = first_turn.timestamp
                except Exception:
                    preview = "(corrupt)"
            summaries.append(SessionSummary(
                id=session_id,
                created=created,
                preview=preview,
                turn_count=turn_count,
            ))
        return summaries
