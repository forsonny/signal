"""Memory engine -- orchestrates storage and index."""

from __future__ import annotations

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.errors import MemoryStoreError
from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.index import MemoryIndex
from signalagent.memory.storage import MemoryStorage

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        instance_dir: Path,
        decay_half_life_days: int = 30,
        embedder: object | None = None,
    ) -> None:
        self._memory_dir = instance_dir / "memory"
        self._storage = MemoryStorage(self._memory_dir)
        self._index = MemoryIndex(self._memory_dir / "index.db")
        self._decay_half_life_days = decay_half_life_days
        self._embedder = embedder

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
        """Write memory to disk, then upsert index, then embed.

        File-first ordering: if index or embedding fails, the file is
        still on disk and rebuild_index()/rebuild_embeddings() can recover.
        """
        path = self._storage.write(memory)
        await self._index.upsert(memory, path)
        if self._embedder is not None:
            try:
                vectors = await self._embedder.embed([memory.content])
                await self._index.store_embedding(memory.id, vectors[0])
            except Exception:
                logger.warning(
                    "Embedding failed for %s, memory stored without vector",
                    memory.id,
                )
        return memory

    async def archive(self, memory_id: str, reason: str) -> None:
        """Archive a memory: append changelog to file, set is_archived in index.

        The memory drops out of default search results. File stays on disk.
        Reversible by manually setting is_archived=0 in the index.
        """
        row = await self._index.get(memory_id)
        if row is None:
            return
        path = Path(row["file_path"])
        try:
            memory = self._storage.read(path)
        except MemoryStoreError:
            await self._index.archive(memory_id)
            return
        now = datetime.now(timezone.utc)
        memory.changelog.append(
            f"v{memory.version + 1}: Archived ({now.date()}, reason: {reason})"
        )
        memory.version += 1
        memory.updated = now
        self._storage.write(memory)
        await self._index.upsert(memory, path)
        await self._index.archive(memory_id)

    async def consolidate(
        self,
        source_ids: list[str],
        new_content: str,
        new_tags: list[str],
        agent: str,
        memory_type: MemoryType,
    ) -> Memory:
        """Create a consolidated memory from sources.

        Creates a new memory with consolidated_from set. For each source:
        updates superseded_by on the file, appends changelog, then archives.
        File-first safety: new memory is created before sources are updated.
        """
        now = datetime.now(timezone.utc)
        new_memory = Memory(
            id=generate_memory_id(),
            agent=agent,
            type=memory_type,
            tags=new_tags,
            content=new_content,
            confidence=0.5,
            version=1,
            created=now,
            updated=now,
            accessed=now,
            access_count=0,
            changelog=[
                f"v1: Consolidated from {source_ids} ({now.date()})"
            ],
            consolidated_from=list(source_ids),
        )

        await self.store(new_memory)

        for sid in source_ids:
            row = await self._index.get(sid)
            if row is None:
                continue
            path = Path(row["file_path"])
            try:
                source = self._storage.read(path)
            except MemoryStoreError:
                continue
            source.superseded_by = new_memory.id
            source.changelog.append(
                f"v{source.version + 1}: Superseded by {new_memory.id} ({now.date()})"
            )
            source.version += 1
            source.updated = now
            self._storage.write(source)
            await self.archive(sid, reason=f"consolidated into {new_memory.id}")

        return new_memory

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

    async def find_groups(
        self,
        agent: str | None = None,
        min_overlap: int = 1,
    ) -> list[list[Memory]]:
        """Find groups of related memories by tag overlap.

        Groups memories by (agent, type), then within each group finds
        connected components where memories share at least min_overlap tags.
        Returns groups of 2+ memories.

        O(n^2) per agent on memory count -- acceptable for weekly maintenance
        runs with capped candidate counts. Phase 9b embeddings enable
        efficient clustering if scale becomes an issue.
        """
        rows = await self._index.list_active(agent=agent)
        memories: list[Memory] = []
        for row in rows:
            try:
                mem = self._storage.read(Path(row["file_path"]))
                memories.append(mem)
            except MemoryStoreError:
                continue

        by_agent_type: dict[tuple[str, str], list[Memory]] = defaultdict(list)
        for mem in memories:
            by_agent_type[(mem.agent, mem.type.value)].append(mem)

        result: list[list[Memory]] = []
        for group in by_agent_type.values():
            if len(group) < 2:
                continue

            n = len(group)
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(x: int, y: int) -> None:
                px, py = find(x), find(y)
                if px != py:
                    parent[px] = py

            for i in range(n):
                tags_i = set(group[i].tags)
                for j in range(i + 1, n):
                    tags_j = set(group[j].tags)
                    if len(tags_i & tags_j) >= min_overlap:
                        union(i, j)

            components: dict[int, list[Memory]] = defaultdict(list)
            for i in range(n):
                components[find(i)].append(group[i])

            for comp in components.values():
                if len(comp) >= 2:
                    result.append(comp)

        return result

    async def find_stale(
        self,
        threshold_days: int,
        min_confidence: float,
    ) -> list[tuple[str, str]]:
        """Find stale memories based on access time and effective confidence.

        A memory is stale when:
        1. days_since_access > threshold_days, AND
        2. effective confidence (confidence * decay_factor) < min_confidence

        Returns list of (memory_id, reason) tuples.
        """
        rows = await self._index.list_active()
        now = datetime.now(timezone.utc)
        stale: list[tuple[str, str]] = []

        for row in rows:
            accessed = datetime.fromisoformat(row["accessed_at"])
            if accessed.tzinfo is None:
                accessed = accessed.replace(tzinfo=timezone.utc)
            days_since = (now - accessed).total_seconds() / 86400

            if days_since < threshold_days:
                continue

            decay_factor = 1.0 / (1.0 + days_since / self._decay_half_life_days)
            effective_conf = row["confidence"] * decay_factor

            if effective_conf < min_confidence:
                reason = (
                    f"stale: {int(days_since)} days without access, "
                    f"effective confidence {effective_conf:.2f}"
                )
                stale.append((row["id"], reason))

        return stale

    async def close(self) -> None:
        """Close the index connection."""
        await self._index.close()
