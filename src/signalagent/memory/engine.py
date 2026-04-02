"""Memory engine -- orchestrates storage and index."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.errors import MemoryStoreError
from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.index import MemoryIndex
from signalagent.memory.storage import MemoryStorage


def generate_memory_id() -> str:
    """Generate a unique memory ID: mem_ + 8 hex chars."""
    return f"mem_{secrets.token_hex(4)}"


class MemoryEngine:
    """Orchestrates MemoryStorage and MemoryIndex.

    This is the public API for memory operations. Nothing outside
    the memory package should touch storage or index directly.

    In Phase 2, the CLI creates a new engine per command invocation
    (open, work, close). When the runtime integrates memory in
    Phase 3+, the engine becomes a long-lived singleton injected
    at startup -- not recreated per operation.
    """

    def __init__(self, instance_dir: Path, decay_half_life_days: int = 30) -> None:
        self._memory_dir = instance_dir / "memory"
        self._storage = MemoryStorage(self._memory_dir)
        self._index = MemoryIndex(self._memory_dir / "index.db")
        self._decay_half_life_days = decay_half_life_days

    async def initialize(self) -> None:
        """Initialize the SQLite index. Call once at startup."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        await self._index.initialize()

    def create_memory(
        self,
        agent: str,
        memory_type: MemoryType,
        tags: list[str],
        content: str,
        confidence: float = 0.5,
    ) -> Memory:
        """Factory: build a Memory with generated ID and timestamps."""
        now = datetime.now(timezone.utc)
        return Memory(
            id=generate_memory_id(),
            agent=agent,
            type=memory_type,
            tags=tags,
            content=content,
            confidence=confidence,
            version=1,
            created=now,
            updated=now,
            accessed=now,
            access_count=0,
            changelog=[
                f"v1: Created ({now.date()}, confidence: {confidence})"
            ],
        )

    async def store(self, memory: Memory) -> Memory:
        """Write memory to disk, then upsert index. Returns the memory.

        File-first ordering: if index write fails, the file is still
        on disk and rebuild_index() can recover it.
        """
        path = self._storage.write(memory)
        await self._index.upsert(memory, path)
        return memory

    async def search(
        self,
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        touch: bool = False,
    ) -> list[Memory]:
        """Search index, load full Memory objects for results.

        Args:
            touch: If True, update access stats for returned memories.
                   Default False -- browsing doesn't inflate scores.
        """
        results = await self._index.search(
            tags=tags,
            agent=agent,
            memory_type=memory_type,
            limit=limit,
            decay_half_life_days=self._decay_half_life_days,
        )
        memories: list[Memory] = []
        for row in results:
            path = Path(row["file_path"])
            try:
                memory = self._storage.read(path)
                memories.append(memory)
                if touch:
                    await self._index.touch(row["id"])
            except MemoryStoreError:
                continue
        return memories

    async def inspect(self, memory_id: str) -> Memory | None:
        """Load a single memory by ID. Touches access stats.

        Returns None if the memory doesn't exist.
        """
        row = await self._index.get(memory_id)
        if row is None:
            return None
        path = Path(row["file_path"])
        try:
            memory = self._storage.read(path)
            await self._index.touch(memory_id)
            return memory
        except MemoryStoreError:
            return None

    async def delete(self, memory_id: str) -> None:
        """Remove from both disk and index."""
        row = await self._index.get(memory_id)
        if row is None:
            return
        self._storage.delete(Path(row["file_path"]))
        await self._index.remove(memory_id)

    async def rebuild_index(self) -> int:
        """Walk all memory files on disk, re-index each one.

        Returns the count of memories indexed. Idempotent.
        Use when the SQLite file is corrupted or missing.
        """
        count = 0
        for file_path, memory in self._storage.scan_all_files():
            await self._index.upsert(memory, file_path)
            count += 1
        return count

    async def close(self) -> None:
        """Close the index connection."""
        await self._index.close()
