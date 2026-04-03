"""Tests for two-phase semantic search."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine


def _make_embedder(vectors: dict[str, list[float]]):
    """Create a mock embedder that returns predetermined vectors."""
    mock = AsyncMock()

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            if text in vectors:
                result.append(vectors[text])
            else:
                result.append([0.0] * len(next(iter(vectors.values()))))
        return result

    mock.embed = AsyncMock(side_effect=fake_embed)
    return mock


@pytest.fixture
async def embedded_engine(tmp_path):
    """Engine with a mock embedder producing known vectors."""
    vectors = {
        "error handling best practices": [1.0, 0.0, 0.0],
        "exception management patterns": [0.95, 0.1, 0.0],
        "python data structures": [0.0, 1.0, 0.0],
        "query about error handling": [0.9, 0.05, 0.0],
    }
    embedder = _make_embedder(vectors)
    eng = MemoryEngine(tmp_path, embedder=embedder)
    await eng.initialize()
    yield eng
    await eng.close()


class TestSemanticSearch:
    async def test_query_finds_semantically_similar(self, embedded_engine):
        """Memories with different tags but similar content are found."""
        eng = embedded_engine
        m1 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["errors"], content="error handling best practices",
        )
        m2 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["exceptions"], content="exception management patterns",
        )
        m3 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["data"], content="python data structures",
        )
        await eng.store(m1)
        await eng.store(m2)
        await eng.store(m3)

        results = await eng.search(
            query="query about error handling", agent="prime", limit=2,
        )
        result_ids = {r.id for r in results}
        assert m1.id in result_ids
        assert m2.id in result_ids
        assert m3.id not in result_ids

    async def test_query_without_tags_uses_embedding_similarity_for_relevance(self, embedded_engine):
        """When query is provided but no tags, embedding similarity is the relevance signal."""
        eng = embedded_engine
        m1 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["errors"], content="error handling best practices",
        )
        m2 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["data"], content="python data structures",
        )
        await eng.store(m1)
        await eng.store(m2)

        results = await eng.search(query="query about error handling", agent="prime")
        assert len(results) >= 1
        assert results[0].id == m1.id

    async def test_search_without_query_uses_tag_path(self, embedded_engine):
        """search() without query uses existing tag-only path."""
        eng = embedded_engine
        m1 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="error handling best practices",
        )
        await eng.store(m1)

        results = await eng.search(tags=["python"])
        assert len(results) == 1
        assert results[0].id == m1.id

    async def test_search_with_tags_and_query(self, embedded_engine):
        """When both tags and query provided, tags used for relevance slot."""
        eng = embedded_engine
        m1 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["errors", "python"], content="error handling best practices",
        )
        m2 = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["exceptions"], content="exception management patterns",
        )
        await eng.store(m1)
        await eng.store(m2)

        results = await eng.search(
            tags=["errors"], query="query about error handling", agent="prime",
        )
        assert results[0].id == m1.id

    async def test_no_embedder_ignores_query(self, tmp_path):
        """When embedder is None, query parameter is silently ignored."""
        eng = MemoryEngine(tmp_path)
        await eng.initialize()
        mem = eng.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["test"], content="test content",
        )
        await eng.store(mem)

        results = await eng.search(tags=["test"], query="anything")
        assert len(results) == 1

        await eng.close()


class TestMixedState:
    async def test_unembedded_memories_invisible_to_semantic_search(self, tmp_path):
        """Memories without embeddings don't appear in semantic search results."""
        vectors = {
            "new memory with embedding": [1.0, 0.0],
            "query text": [0.9, 0.1],
        }
        embedder = _make_embedder(vectors)

        # Create engine WITHOUT embedder first, store a memory
        eng_no_embed = MemoryEngine(tmp_path)
        await eng_no_embed.initialize()
        old_mem = eng_no_embed.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["old"], content="old memory without embedding",
        )
        await eng_no_embed.store(old_mem)
        await eng_no_embed.close()

        # Re-open WITH embedder, store a new memory
        eng_with_embed = MemoryEngine(tmp_path, embedder=embedder)
        await eng_with_embed.initialize()
        new_mem = eng_with_embed.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["new"], content="new memory with embedding",
        )
        await eng_with_embed.store(new_mem)

        # Semantic search should only find the new embedded memory
        results = await eng_with_embed.search(query="query text", agent="prime")
        result_ids = {r.id for r in results}
        assert new_mem.id in result_ids
        assert old_mem.id not in result_ids

        # Tag search should still find the old memory
        tag_results = await eng_with_embed.search(tags=["old"])
        assert len(tag_results) == 1
        assert tag_results[0].id == old_mem.id

        await eng_with_embed.close()
