"""Tests for MemoryEngine.consolidate()."""

import pytest

from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine


@pytest.fixture
async def engine(tmp_path):
    eng = MemoryEngine(tmp_path)
    await eng.initialize()
    yield eng
    await eng.close()


class TestConsolidate:
    async def test_creates_new_memory(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        new = await engine.consolidate(
            source_ids=[m1.id, m2.id],
            new_content="combined lesson",
            new_tags=["python", "lessons"],
            agent="prime",
            memory_type=MemoryType.LEARNING,
        )
        assert new.id.startswith("mem_")
        assert new.content == "combined lesson"
        assert new.consolidated_from == [m1.id, m2.id]
        assert "Consolidated from" in new.changelog[0]

    async def test_archives_sources(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        await engine.consolidate(
            source_ids=[m1.id, m2.id],
            new_content="combined",
            new_tags=["python"],
            agent="prime",
            memory_type=MemoryType.LEARNING,
        )
        row1 = await engine._index.get(m1.id)
        row2 = await engine._index.get(m2.id)
        assert row1["is_archived"] == 1
        assert row2["is_archived"] == 1

    async def test_sets_superseded_by_on_sources(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        new = await engine.consolidate(
            source_ids=[m1.id, m2.id],
            new_content="combined",
            new_tags=["python"],
            agent="prime",
            memory_type=MemoryType.LEARNING,
        )
        path1 = engine._storage.resolve_path(m1)
        updated1 = engine._storage.read(path1)
        assert updated1.superseded_by == new.id
        assert any("Superseded by" in c for c in updated1.changelog)

    async def test_new_memory_searchable(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        await engine.store(m1)
        await engine.consolidate(
            source_ids=[m1.id],
            new_content="combined",
            new_tags=["python", "consolidated"],
            agent="prime",
            memory_type=MemoryType.LEARNING,
        )
        results = await engine.search(tags=["consolidated"])
        assert len(results) == 1
        assert results[0].content == "combined"

    async def test_skips_missing_source(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        await engine.store(m1)
        new = await engine.consolidate(
            source_ids=[m1.id, "mem_nonexist"],
            new_content="combined",
            new_tags=["python"],
            agent="prime",
            memory_type=MemoryType.LEARNING,
        )
        assert new is not None
        row = await engine._index.get(m1.id)
        assert row["is_archived"] == 1
