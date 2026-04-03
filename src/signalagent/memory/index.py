"""SQLite metadata index for memory retrieval.

Stores metadata and embedding vectors in SQLite for fast lookups.
Content stays on disk as markdown files -- the index only holds what's
needed for search and scoring.
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from signalagent.core.models import Memory
from signalagent.memory.scoring import compute_frequency_score, compute_score

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS memory_index (
    id            TEXT PRIMARY KEY,
    agent         TEXT NOT NULL,
    type          TEXT NOT NULL,
    tags          TEXT NOT NULL,
    confidence    REAL NOT NULL,
    version       INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    accessed_at   TEXT NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0,
    file_path     TEXT NOT NULL,
    superseded_by TEXT,
    is_archived   INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_EMBEDDINGS_TABLE = """\
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id        TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    FOREIGN KEY (id) REFERENCES memory_index(id)
);
"""

_UPSERT = """\
INSERT INTO memory_index
    (id, agent, type, tags, confidence, version,
     created_at, updated_at, accessed_at, access_count,
     file_path, superseded_by, is_archived)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    agent=excluded.agent, type=excluded.type, tags=excluded.tags,
    confidence=excluded.confidence, version=excluded.version,
    updated_at=excluded.updated_at, accessed_at=excluded.accessed_at,
    access_count=excluded.access_count, file_path=excluded.file_path,
    superseded_by=excluded.superseded_by, is_archived=excluded.is_archived
"""


class MemoryIndex:
    """Async SQLite index for memory metadata.

    Stores metadata only -- never content. Enables fast lookup
    by tags, agent, and type with recency-based scoring.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialise the index.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the database connection and create tables if needed."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(_CREATE_TABLE)
        await self._db.execute(_CREATE_EMBEDDINGS_TABLE)
        await self._db.commit()

    async def upsert(self, memory: Memory, file_path: str | Path) -> None:
        """Insert or update an index entry from a Memory object.

        Args:
            memory: Memory whose metadata to index.
            file_path: On-disk path to the memory's markdown file.
        """
        assert self._db is not None
        await self._db.execute(
            _UPSERT,
            (
                memory.id,
                memory.agent,
                memory.type.value,
                json.dumps(memory.tags),
                memory.confidence,
                memory.version,
                memory.created.isoformat(),
                memory.updated.isoformat(),
                memory.accessed.isoformat(),
                memory.access_count,
                str(file_path),
                memory.superseded_by,
                0,
            ),
        )
        await self._db.commit()

    async def remove(self, memory_id: str) -> None:
        """Delete an entry from the index.

        Args:
            memory_id: ID of the memory to remove.
        """
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM memory_index WHERE id = ?", (memory_id,)
        )
        await self._db.commit()

    async def get(self, memory_id: str) -> dict | None:
        """Fetch a single index row by ID.

        Args:
            memory_id: ID of the memory to fetch.

        Returns:
            Row dict, or None if not found.
        """
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM memory_index WHERE id = ?", (memory_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def search(
        self,
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        include_archived: bool = False,
        decay_half_life_days: int = 30,
    ) -> list[dict]:
        """Tag-match + decay-scored search. Returns ranked results.

        Scoring formula:
            base_score = tag * 0.5 + frequency * 0.25 + confidence * 0.25
            decay_factor = 1 / (1 + days_since / decay_half_life_days)
            effective_score = base_score * decay_factor

        Args:
            tags: Tags to match against. Memories must share at least one tag.
            agent: Filter to a specific agent name.
            memory_type: Filter to a specific memory type string.
            limit: Maximum number of results to return.
            include_archived: If True, include archived memories.
            decay_half_life_days: Days after which relevance is halved.
                Shorter values penalise stale memories more aggressively.
        """
        assert self._db is not None

        conditions: list[str] = []
        params: list[str | int] = []

        if not include_archived:
            conditions.append("m.is_archived = 0")

        if agent:
            conditions.append("m.agent = ?")
            params.append(agent)

        if memory_type:
            conditions.append("m.type = ?")
            params.append(memory_type)

        if tags:
            placeholders = ", ".join("?" for _ in tags)
            conditions.append(
                f"EXISTS (SELECT 1 FROM json_each(m.tags) jt"
                f" WHERE jt.value IN ({placeholders}))"
            )
            params.extend(tags)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM memory_index m WHERE {where}"

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        results = [dict(row) for row in rows]

        now = datetime.now(timezone.utc)
        query_tags = set(tags) if tags else set()

        for row in results:
            row_tags = set(json.loads(row["tags"]))

            if query_tags:
                relevance = len(row_tags & query_tags) / len(query_tags)
            else:
                relevance = 0.0

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
                decay_half_life_days=decay_half_life_days,
            )

        results.sort(key=lambda r: r["_score"], reverse=True)
        return results[:limit]

    async def touch(self, memory_id: str) -> None:
        """Update accessed_at and increment access_count.

        Args:
            memory_id: ID of the memory to touch.
        """
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE memory_index SET accessed_at = ?,"
            " access_count = access_count + 1 WHERE id = ?",
            (now, memory_id),
        )
        await self._db.commit()

    async def archive(self, memory_id: str) -> None:
        """Mark a memory as archived. It will no longer appear in default searches.

        Args:
            memory_id: ID of the memory to archive.
        """
        assert self._db is not None
        await self._db.execute(
            "UPDATE memory_index SET is_archived = 1 WHERE id = ?",
            (memory_id,),
        )
        await self._db.commit()

    async def list_active(self, agent: str | None = None) -> list[dict]:
        """Return all non-archived index rows, optionally filtered by agent.

        No scoring -- used by maintenance operations (find_groups, find_stale).
        O(n) on total memory count per agent.

        Args:
            agent: Optional agent name filter.

        Returns:
            List of row dicts for all active memories.
        """
        assert self._db is not None
        conditions = ["is_archived = 0"]
        params: list[str] = []
        if agent:
            conditions.append("agent = ?")
            params.append(agent)
        where = " AND ".join(conditions)
        cursor = await self._db.execute(
            f"SELECT * FROM memory_index WHERE {where}", params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def store_embedding(self, memory_id: str, vector: list[float]) -> None:
        """Store an embedding vector as a BLOB.

        Args:
            memory_id: ID of the memory this embedding belongs to.
            vector: Float vector to store.
        """
        assert self._db is not None
        blob = struct.pack(f"{len(vector)}f", *vector)
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_embeddings (id, embedding) VALUES (?, ?)",
            (memory_id, blob),
        )
        await self._db.commit()

    async def get_embedding(self, memory_id: str) -> list[float] | None:
        """Retrieve an embedding vector by memory ID.

        Args:
            memory_id: ID of the memory whose embedding to fetch.

        Returns:
            Float vector, or None if no embedding is stored.
        """
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT embedding FROM memory_embeddings WHERE id = ?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        blob = row[0]
        count = len(blob) // 4  # 4 bytes per float
        return list(struct.unpack(f"{count}f", blob))

    async def get_all_embeddings(
        self,
        agent: str | None = None,
        include_archived: bool = False,
    ) -> list[tuple[str, list[float]]]:
        """Return (id, vector) pairs for memories with embeddings.

        Uses SQL JOIN to filter by agent and exclude archived --
        filtering happens in SQL, not after loading BLOBs into Python.

        Args:
            agent: Optional agent name filter.
            include_archived: Whether to include archived memories.

        Returns:
            List of (memory_id, vector) tuples.
        """
        assert self._db is not None
        conditions = []
        params: list[str] = []

        if not include_archived:
            conditions.append("m.is_archived = 0")

        if agent:
            conditions.append("m.agent = ?")
            params.append(agent)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = (
            "SELECT e.id, e.embedding FROM memory_embeddings e "
            f"JOIN memory_index m ON e.id = m.id WHERE {where}"
        )
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        results: list[tuple[str, list[float]]] = []
        for row in rows:
            blob = row[1]
            count = len(blob) // 4
            vector = list(struct.unpack(f"{count}f", blob))
            results.append((row[0], vector))
        return results

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
