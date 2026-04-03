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
        """Create a manifest backed by *worktrees_dir*/``manifest.jsonl``.

        Args:
            worktrees_dir: Directory that stores the manifest file.
                Created on init if it does not exist.
        """
        self._path = worktrees_dir / "manifest.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: WorktreeRecord) -> None:
        """Append a record to the manifest.

        Args:
            record: The worktree record to persist.
        """
        with open(self._path, "a") as f:
            f.write(record.model_dump_json() + "\n")

    def load(self) -> dict[str, WorktreeRecord]:
        """Load all records from disk. Last entry per ID wins.

        Returns:
            Dictionary mapping worktree IDs to their latest record.
        """
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
        """Get the resolved record for a worktree ID.

        Args:
            worktree_id: The unique worktree identifier to look up.

        Returns:
            The matching ``WorktreeRecord``, or ``None`` if not found.
        """
        return self.load().get(worktree_id)

    def list_pending(self) -> list[WorktreeRecord]:
        """Return pending worktrees, newest first.

        Returns:
            List of ``WorktreeRecord`` entries with ``status="pending"``,
            sorted by creation time in descending order.
        """
        records = self.load()
        return sorted(
            [r for r in records.values() if r.status == "pending"],
            key=lambda r: r.created,
            reverse=True,
        )
