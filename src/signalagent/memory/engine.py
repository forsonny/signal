"""Memory engine -- orchestrates storage and index.

Provides the public API for all memory operations. Nothing outside the
memory package should touch MemoryStorage or MemoryIndex directly.
"""

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
from signalagent.memory.scoring import compute_frequency_score, compute_score
from signalagent.memory.similarity import cosine_similarity
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
        """Initialise the memory engine.

        Args:
            instance_dir: Root instance directory containing the ``memory/``
                subdirectory.
            decay_half_life_days: Days after which a memory's relevance
                score is halved.
            embedder: Optional embedding provider (EmbeddingProtocol) for
                semantic search. None disables embedding.
        """
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
        """Factory: build a Memory with generated ID and timestamps.

        Args:
            agent: Owning agent name.
            memory_type: Category of the new memory.
            tags: Searchable tags.
            content: Textual content of the memory.
            confidence: Initial confidence score (0.0-1.0).

        Returns:
            A new Memory instance ready for ``store()``.
        """
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

        Args:
            memory: Memory object to persist.

        Returns:
            The same Memory instance (unchanged).
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

        Args:
            memory_id: ID of the memory to archive.
            reason: Human-readable reason stored in the changelog.
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

        Args:
            source_ids: IDs of the memories to consolidate.
            new_content: Merged content for the new memory.
            new_tags: Tags for the consolidated memory.
            agent: Owning agent name.
            memory_type: Type of the consolidated memory.

        Returns:
            The newly created consolidated Memory.
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
        query: str | None = None,
    ) -> list[Memory]:
        """Search index, load full Memory objects for results.

        When query is provided and an embedder is available, uses two-phase
        retrieval: embedding similarity selects candidates, then the existing
        scoring formula ranks them. Otherwise falls back to tag-only search.

        Args:
            touch: If True, update access stats for returned memories.
            query: Text to embed for semantic search. Optional.
        """
        if query and self._embedder is not None:
            return await self._search_semantic(
                query=query, tags=tags, agent=agent,
                memory_type=memory_type, limit=limit, touch=touch,
            )

        # Tag-only path (existing behavior)
        results = await self._index.search(
            tags=tags,
            agent=agent,
            memory_type=memory_type,
            limit=limit,
            decay_half_life_days=self._decay_half_life_days,
        )
        return await self._load_results(results, touch=touch)

    async def _search_semantic(
        self,
        query: str,
        tags: list[str] | None,
        agent: str | None,
        memory_type: str | None,
        limit: int,
        touch: bool,
    ) -> list[Memory]:
        """Two-phase retrieval: embed query -> cosine candidates -> score -> rank.

        Uses the shared scoring formula from memory.scoring (same weights as
        MemoryIndex.search) -- one source of truth for the scoring math.
        """
        import json

        # Phase 1: embed query and find candidates
        query_vectors = await self._embedder.embed([query])
        query_vector = query_vectors[0]

        all_embeddings = await self._index.get_all_embeddings(
            agent=agent, include_archived=False,
        )
        if not all_embeddings:
            return []

        # Compute similarities and take top N candidates
        candidate_limit = limit * 3
        scored = []
        for mem_id, vector in all_embeddings:
            sim = cosine_similarity(query_vector, vector)
            scored.append((mem_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = scored[:candidate_limit]

        if not candidates:
            return []

        # Build similarity lookup for Phase 2
        sim_by_id = {mem_id: sim for mem_id, sim in candidates}
        candidate_ids = set(sim_by_id.keys())

        # Phase 2: score candidates with shared formula
        now = datetime.now(timezone.utc)
        query_tags = set(tags) if tags else set()

        scored_rows: list[dict] = []
        for mem_id in candidate_ids:
            row = await self._index.get(mem_id)
            if row is None or row.get("is_archived", 0):
                continue
            if memory_type and row["type"] != memory_type:
                continue

            row_tags = set(json.loads(row["tags"]))
            if query_tags:
                relevance = len(row_tags & query_tags) / len(query_tags)
            else:
                relevance = sim_by_id[mem_id]

            frequency_score = compute_frequency_score(row["access_count"])

            accessed = datetime.fromisoformat(row["accessed_at"])
            if accessed.tzinfo is None:
                accessed = accessed.replace(tzinfo=timezone.utc)
            days_since = max((now - accessed).total_seconds() / 86400, 0)

            row["_score"] = compute_score(
                relevance=relevance,
                frequency_score=frequency_score,
                confidence=row["confidence"],
                days_since_access=days_since,
                decay_half_life_days=self._decay_half_life_days,
            )
            scored_rows.append(row)

        scored_rows.sort(key=lambda r: r["_score"], reverse=True)
        return await self._load_results(scored_rows[:limit], touch=touch)

    async def _load_results(
        self, rows: list[dict], touch: bool = False,
    ) -> list[Memory]:
        """Load Memory objects from index rows."""
        memories: list[Memory] = []
        for row in rows:
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

        Args:
            memory_id: ID of the memory to inspect.

        Returns:
            The Memory object, or None if not found.
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
        """Remove from both disk and index.

        Args:
            memory_id: ID of the memory to delete permanently.
        """
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

        Args:
            agent: Optional agent name filter.
            min_overlap: Minimum shared tags to consider memories related.

        Returns:
            List of memory groups, each containing 2+ related memories.
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

        Args:
            threshold_days: Minimum days without access to consider.
            min_confidence: Effective confidence threshold below which
                the memory is considered stale.

        Returns:
            List of (memory_id, reason) tuples.
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

    async def rebuild_embeddings(self, batch_size: int = 50) -> int:
        """Backfill embedding vectors for memories that lack them.

        Processes in batches to respect embedding API limits.

        Args:
            batch_size: Number of memories to embed per API call.

        Returns:
            Count of memories that were newly embedded.
        """
        if self._embedder is None:
            return 0

        count = 0
        batch_ids: list[str] = []
        batch_contents: list[str] = []

        for file_path, memory in self._storage.scan_all_files():
            existing = await self._index.get_embedding(memory.id)
            if existing is not None:
                continue
            batch_ids.append(memory.id)
            batch_contents.append(memory.content)

            if len(batch_contents) >= batch_size:
                vectors = await self._embedder.embed(batch_contents)
                for mid, vec in zip(batch_ids, vectors):
                    await self._index.store_embedding(mid, vec)
                count += len(batch_ids)
                batch_ids.clear()
                batch_contents.clear()

        # Final partial batch
        if batch_contents:
            vectors = await self._embedder.embed(batch_contents)
            for mid, vec in zip(batch_ids, vectors):
                await self._index.store_embedding(mid, vec)
            count += len(batch_ids)

        return count

    async def close(self) -> None:
        """Close the index connection."""
        await self._index.close()
