"""Tests for MemoryIndex embedding storage."""

from datetime import datetime, timezone

import pytest

from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.index import MemoryIndex


def _make_memory(**overrides) -> Memory:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="mem_test1234", agent="prime", type=MemoryType.IDENTITY,
        tags=["python"], content="test content",
        confidence=0.8, version=1, created=now, updated=now, accessed=now,
    )
    defaults.update(overrides)
    return Memory(**defaults)


@pytest.fixture
async def index():
    idx = MemoryIndex(":memory:")
    await idx.initialize()
    yield idx
    await idx.close()


class TestStoreEmbedding:
    async def test_store_and_retrieve(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        vector = [0.1, 0.2, 0.3, 0.4]
        await index.store_embedding("mem_test1234", vector)
        result = await index.get_embedding("mem_test1234")
        assert result is not None
        assert len(result) == 4
        assert abs(result[0] - 0.1) < 1e-6
        assert abs(result[3] - 0.4) < 1e-6

    async def test_replace_existing(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        await index.store_embedding("mem_test1234", [0.1, 0.2])
        await index.store_embedding("mem_test1234", [0.9, 0.8])
        result = await index.get_embedding("mem_test1234")
        assert abs(result[0] - 0.9) < 1e-6

    async def test_get_nonexistent_returns_none(self, index):
        result = await index.get_embedding("mem_nonexist")
        assert result is None


class TestGetAllEmbeddings:
    async def test_returns_all_active(self, index):
        for i in range(3):
            mem = _make_memory(id=f"mem_{i:08x}")
            await index.upsert(mem, f"/fake/{i}.md")
            await index.store_embedding(f"mem_{i:08x}", [float(i), float(i + 1)])
        results = await index.get_all_embeddings()
        assert len(results) == 3

    async def test_excludes_archived(self, index):
        m1 = _make_memory(id="mem_11111111")
        m2 = _make_memory(id="mem_22222222")
        await index.upsert(m1, "/fake/1.md")
        await index.upsert(m2, "/fake/2.md")
        await index.store_embedding("mem_11111111", [0.1])
        await index.store_embedding("mem_22222222", [0.2])
        await index.archive("mem_11111111")
        results = await index.get_all_embeddings()
        assert len(results) == 1
        assert results[0][0] == "mem_22222222"

    async def test_filters_by_agent(self, index):
        m1 = _make_memory(id="mem_11111111", agent="prime")
        m2 = _make_memory(id="mem_22222222", agent="code-review")
        await index.upsert(m1, "/fake/1.md")
        await index.upsert(m2, "/fake/2.md")
        await index.store_embedding("mem_11111111", [0.1])
        await index.store_embedding("mem_22222222", [0.2])
        results = await index.get_all_embeddings(agent="prime")
        assert len(results) == 1
        assert results[0][0] == "mem_11111111"

    async def test_returns_id_and_vector_tuples(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        await index.store_embedding("mem_test1234", [0.5, 0.6])
        results = await index.get_all_embeddings()
        assert len(results) == 1
        mem_id, vector = results[0]
        assert mem_id == "mem_test1234"
        assert len(vector) == 2

    async def test_skips_memories_without_embeddings(self, index):
        m1 = _make_memory(id="mem_11111111")
        m2 = _make_memory(id="mem_22222222")
        await index.upsert(m1, "/fake/1.md")
        await index.upsert(m2, "/fake/2.md")
        await index.store_embedding("mem_11111111", [0.1])
        # m2 has no embedding
        results = await index.get_all_embeddings()
        assert len(results) == 1
        assert results[0][0] == "mem_11111111"
