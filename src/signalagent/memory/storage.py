"""Atomic markdown file storage for memories."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from signalagent.core.errors import MemoryStoreError
from signalagent.core.models import Memory
from signalagent.core.types import MemoryType


class MemoryStorage:
    """Reads and writes Memory objects as markdown files with YAML frontmatter.

    Each memory is one file. Content stays on disk, never in the index.
    """

    def __init__(self, memory_root: Path) -> None:
        self._root = memory_root

    def resolve_path(self, memory: Memory) -> Path:
        """Determine file path from agent + type + id.

        Routing rules:
        - type == SHARED   -> shared/{id}.md       (agent ignored)
        - agent == "prime"  -> prime/{type}/{id}.md
        - otherwise         -> micro/{agent}/{type}/{id}.md
        """
        if memory.type == MemoryType.SHARED:
            return self._root / "shared" / f"{memory.id}.md"
        if memory.agent == "prime":
            return self._root / "prime" / memory.type.value / f"{memory.id}.md"
        return (
            self._root / "micro" / memory.agent / memory.type.value / f"{memory.id}.md"
        )

    def write(self, memory: Memory) -> Path:
        """Write memory to disk as atomic markdown file. Returns file path."""
        path = self.resolve_path(memory)
        path.parent.mkdir(parents=True, exist_ok=True)

        frontmatter = {
            "id": memory.id,
            "agent": memory.agent,
            "type": memory.type.value,
            "tags": memory.tags,
            "confidence": memory.confidence,
            "version": memory.version,
            "created": memory.created.isoformat(),
            "updated": memory.updated.isoformat(),
            "accessed": memory.accessed.isoformat(),
            "access_count": memory.access_count,
            "changelog": memory.changelog,
            "supersedes": memory.supersedes,
            "superseded_by": memory.superseded_by,
            "consolidated_from": memory.consolidated_from,
        }

        text = "---\n"
        text += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        text += "---\n\n"
        text += memory.content + "\n"

        # Atomic write: temp file then os.replace (crash-safe)
        tmp_path = path.with_suffix(".md.tmp")
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(str(tmp_path), str(path))

        return path

    def read(self, file_path: Path) -> Memory:
        """Read a memory file, parse YAML frontmatter + markdown content.

        Assumes exactly two ``---`` markers produced by write(). Content
        must not contain a bare ``---`` on its own line (e.g., a markdown
        horizontal rule) or the parse will split incorrectly.
        """
        if not file_path.exists():
            raise MemoryStoreError(f"Memory file not found: {file_path}")

        text = file_path.read_text(encoding="utf-8")

        parts = text.split("---", 2)
        if len(parts) < 3:
            raise MemoryStoreError(f"Invalid memory file format: {file_path}")

        frontmatter = yaml.safe_load(parts[1])
        if not isinstance(frontmatter, dict):
            raise MemoryStoreError(f"Invalid memory file format: {file_path}")

        content = parts[2].strip()
        return Memory(**frontmatter, content=content)

    def delete(self, file_path: Path) -> None:
        """Remove a memory file from disk."""
        if file_path.exists():
            file_path.unlink()

    def scan_all_files(self) -> list[tuple[Path, Memory]]:
        """Walk the memory directory tree and parse every .md file.

        Returns a list of (file_path, Memory) pairs. Skips files that
        fail to parse. Used by MemoryEngine.rebuild_index() to re-index
        all memories without reaching into storage internals.
        """
        results: list[tuple[Path, Memory]] = []
        for md_file in self._root.rglob("*.md"):
            try:
                memory = self.read(md_file)
                results.append((md_file, memory))
            except MemoryStoreError:
                continue
        return results
