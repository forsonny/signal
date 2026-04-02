"""Tests for MemoryEngine.archive()."""

import pytest

from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine


@pytest.fixture
async def engine(tmp_path):
    eng = MemoryEngine(tmp_path)
    await eng.initialize()
    yield eng
    await eng.close()


class TestArchive:
    async def test_archive_sets_index_flag(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["test"], content="test content",
        )
        await engine.store(mem)
        await engine.archive(mem.id, reason="stale: 100 days")
        row = await engine._index.get(mem.id)
        assert row["is_archived"] == 1

    async def test_archive_appends_changelog(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["test"], content="test content",
        )
        await engine.store(mem)
        await engine.archive(mem.id, reason="stale: 100 days")
        path = engine._storage.resolve_path(mem)
        updated = engine._storage.read(path)
        assert len(updated.changelog) == 2
        assert "Archived" in updated.changelog[1]
        assert "stale: 100 days" in updated.changelog[1]

    async def test_archive_increments_version(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["test"], content="test content",
        )
        await engine.store(mem)
        await engine.archive(mem.id, reason="test")
        path = engine._storage.resolve_path(mem)
        updated = engine._storage.read(path)
        assert updated.version == 2

    async def test_archive_hides_from_search(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["python"], content="test content",
        )
        await engine.store(mem)
        await engine.archive(mem.id, reason="test")
        results = await engine.search(tags=["python"])
        assert len(results) == 0

    async def test_archive_file_stays_on_disk(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["test"], content="test content",
        )
        await engine.store(mem)
        path = engine._storage.resolve_path(mem)
        await engine.archive(mem.id, reason="test")
        assert path.exists()

    async def test_archive_syncs_version_to_index(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.IDENTITY,
            tags=["test"], content="test content",
        )
        await engine.store(mem)
        await engine.archive(mem.id, reason="test")
        row = await engine._index.get(mem.id)
        assert row["version"] == 2

    async def test_archive_nonexistent_is_noop(self, engine):
        await engine.archive("mem_nonexist", reason="test")
