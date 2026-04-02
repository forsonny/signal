"""JSONL manifest for tracking worktree lifecycle."""
from __future__ import annotations

import logging
from pathlib import Path

from signalagent.worktrees.models import WorktreeRecord

logger = logging.getLogger(__name__)


class WorktreeManifest:
    """Append-only JSONL manifest for worktree records.

    Status updates are appended as new lines. Reader builds a
    dict[id, record] by iterating all lines -- later entries
    overwrite earlier ones for the same ID.
    """

    def __init__(self, worktrees_dir: Path) -> None:
        self._path = worktrees_dir / "manifest.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: WorktreeRecord) -> None:
        """Append a record to the manifest."""
        with open(self._path, "a") as f:
            f.write(record.model_dump_json() + "\n")

    def load(self) -> dict[str, WorktreeRecord]:
        """Load all records. Last entry per ID wins."""
        if not self._path.exists():
            return {}
        records: dict[str, WorktreeRecord] = {}
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = WorktreeRecord.model_validate_json(line)
                records[record.id] = record
            except Exception:
                logger.warning("Skipping malformed manifest line: %s", line[:80])
        return records

    def get(self, worktree_id: str) -> WorktreeRecord | None:
        """Get the resolved record for a worktree ID."""
        return self.load().get(worktree_id)

    def list_pending(self) -> list[WorktreeRecord]:
        """Return pending worktrees, newest first."""
        records = self.load()
        return sorted(
            [r for r in records.values() if r.status == "pending"],
            key=lambda r: r.created,
            reverse=True,
        )
