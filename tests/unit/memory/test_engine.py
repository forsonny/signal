"""Unit tests for MemoryEngine -- storage + index together."""

import pytest

from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine, generate_memory_id


@pytest.fixture
async def engine(tmp_path):
    """Engine backed by real tmp_path filesystem + SQLite."""
    eng = MemoryEngine(tmp_path)
    await eng.initialize()
    yield eng
    await eng.close()


class TestGenerateId:
    def test_starts_with_prefix(self):
        mid = generate_memory_id()
        assert mid.startswith("mem_")

    def test_correct_length(self):
        mid = generate_memory_id()
        assert len(mid) == 12  # "mem_" (4) + 8 hex chars

    def test_unique(self):
        ids = {generate_memory_id() for _ in range(100)}
        assert len(ids) == 100


class TestCreateMemory:
    def test_generates_id(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test content",
        )
        assert mem.id.startswith("mem_")
        assert len(mem.id) == 12

    def test_sets_timestamps(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=[],
            content="test",
        )
        assert mem.created == mem.updated == mem.accessed

    def test_sets_defaults(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=[],
            content="test",
        )
        assert mem.confidence == 0.5
        assert mem.version == 1
        assert mem.access_count == 0
        assert len(mem.changelog) == 1
        assert mem.changelog[0].startswith("v1: Created")

    def test_custom_confidence(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=[],
            content="test",
            confidence=0.9,
        )
        assert mem.confidence == 0.9


class TestStoreAndInspect:
    async def test_store_writes_file_and_indexes(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test content",
        )
        stored = await engine.store(mem)
        assert stored.id == mem.id
        path = engine._storage.resolve_path(mem)
        assert path.exists()

    async def test_inspect_returns_memory(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test content",
        )
        await engine.store(mem)
        loaded = await engine.inspect(mem.id)
        assert loaded is not None
        assert loaded.id == mem.id
        assert loaded.content == "test content"

    async def test_inspect_touches_access_stats(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test content",
        )
        await engine.store(mem)
        await engine.inspect(mem.id)
        row = await engine._index.get(mem.id)
        assert row["access_count"] == 1

    async def test_inspect_nonexistent_returns_none(self, engine):
        loaded = await engine.inspect("mem_nonexist")
        assert loaded is None


class TestSearch:
    async def test_search_returns_memories(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["python"],
            content="test content",
        )
        await engine.store(mem)
        results = await engine.search(tags=["python"])
        assert len(results) == 1
        assert results[0].content == "test content"

    async def test_search_by_tags_filters(self, engine):
        mem1 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["python"],
            content="python stuff",
        )
        mem2 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["javascript"],
            content="js stuff",
        )
        await engine.store(mem1)
        await engine.store(mem2)
        results = await engine.search(tags=["python"])
        assert len(results) == 1
        assert results[0].content == "python stuff"

    async def test_search_no_touch_by_default(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test",
        )
        await engine.store(mem)
        await engine.search(tags=["test"])
        row = await engine._index.get(mem.id)
        assert row["access_count"] == 0

    async def test_search_touch_updates_stats(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test",
        )
        await engine.store(mem)
        await engine.search(tags=["test"], touch=True)
        row = await engine._index.get(mem.id)
        assert row["access_count"] == 1


class TestDelete:
    async def test_delete_removes_file_and_index(self, engine):
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.IDENTITY,
            tags=["test"],
            content="test",
        )
        await engine.store(mem)
        path = engine._storage.resolve_path(mem)
        assert path.exists()

        await engine.delete(mem.id)
        assert not path.exists()
        row = await engine._index.get(mem.id)
        assert row is None

    async def test_delete_nonexistent_is_noop(self, engine):
        await engine.delete("mem_nonexist")  # should not raise


class TestRebuildIndex:
    async def test_rebuild_indexes_all_files(self, engine):
        mems = []
        for i in range(3):
            mem = engine.create_memory(
                agent="prime",
                memory_type=MemoryType.IDENTITY,
                tags=["test"],
                content=f"content {i}",
            )
            await engine.store(mem)
            mems.append(mem)

        # Wipe the index
        await engine._index._db.execute("DELETE FROM memory_index")
        await engine._index._db.commit()

        # Verify index is empty
        results = await engine.search()
        assert len(results) == 0

        # Rebuild
        count = await engine.rebuild_index()
        assert count == 3

        # Verify all memories are back
        results = await engine.search()
        assert len(results) == 3
