"""Tests for MemoryEngine.find_groups() and find_stale()."""

from datetime import datetime, timedelta, timezone

import pytest

from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine


@pytest.fixture
async def engine(tmp_path):
    eng = MemoryEngine(tmp_path)
    await eng.initialize()
    yield eng
    await eng.close()


class TestFindGroups:
    async def test_groups_by_shared_tags(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python", "errors"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python", "testing"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        groups = await engine.find_groups()
        assert len(groups) == 1
        assert len(groups[0]) == 2

    async def test_no_groups_without_overlap(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["javascript"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        groups = await engine.find_groups()
        assert len(groups) == 0

    async def test_separates_by_agent(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="prime lesson",
        )
        m2 = engine.create_memory(
            agent="code-review", memory_type=MemoryType.LEARNING,
            tags=["python"], content="reviewer lesson",
        )
        await engine.store(m1)
        await engine.store(m2)
        groups = await engine.find_groups()
        assert len(groups) == 0

    async def test_separates_by_type(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="learning",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.PATTERN,
            tags=["python"], content="pattern",
        )
        await engine.store(m1)
        await engine.store(m2)
        groups = await engine.find_groups()
        assert len(groups) == 0

    async def test_min_overlap_parameter(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python", "errors", "debugging"], content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)
        groups_1 = await engine.find_groups(min_overlap=1)
        assert len(groups_1) == 1
        groups_2 = await engine.find_groups(min_overlap=2)
        assert len(groups_2) == 0

    async def test_excludes_archived(self, engine):
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
        await engine.archive(m1.id, reason="test")
        groups = await engine.find_groups()
        assert len(groups) == 0

    async def test_filters_by_agent(self, engine):
        m1 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="prime 1",
        )
        m2 = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="prime 2",
        )
        m3 = engine.create_memory(
            agent="code-review", memory_type=MemoryType.LEARNING,
            tags=["python"], content="reviewer 1",
        )
        m4 = engine.create_memory(
            agent="code-review", memory_type=MemoryType.LEARNING,
            tags=["python"], content="reviewer 2",
        )
        for m in [m1, m2, m3, m4]:
            await engine.store(m)
        groups = await engine.find_groups(agent="prime")
        assert len(groups) == 1
        ids = {m.id for m in groups[0]}
        assert m1.id in ids
        assert m2.id in ids


class TestFindStale:
    async def test_finds_stale_memories(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="old lesson",
            confidence=0.3,
        )
        mem.accessed = datetime.now(timezone.utc) - timedelta(days=100)
        await engine.store(mem)
        stale = await engine.find_stale(threshold_days=90, min_confidence=0.1)
        assert len(stale) == 1
        assert stale[0][0] == mem.id
        assert "stale" in stale[0][1]

    async def test_ignores_recent_memories(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="fresh lesson",
            confidence=0.3,
        )
        await engine.store(mem)
        stale = await engine.find_stale(threshold_days=90, min_confidence=0.1)
        assert len(stale) == 0

    async def test_ignores_high_effective_confidence(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="old but confident",
            confidence=0.95,
        )
        mem.accessed = datetime.now(timezone.utc) - timedelta(days=100)
        await engine.store(mem)
        stale = await engine.find_stale(threshold_days=90, min_confidence=0.1)
        assert len(stale) == 0

    async def test_excludes_already_archived(self, engine):
        mem = engine.create_memory(
            agent="prime", memory_type=MemoryType.LEARNING,
            tags=["python"], content="already archived",
            confidence=0.1,
        )
        mem.accessed = datetime.now(timezone.utc) - timedelta(days=200)
        await engine.store(mem)
        await engine.archive(mem.id, reason="test")
        stale = await engine.find_stale(threshold_days=90, min_confidence=0.1)
        assert len(stale) == 0
