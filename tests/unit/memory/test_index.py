"""Unit tests for MemoryIndex -- in-memory SQLite, no filesystem."""

from datetime import datetime, timedelta, timezone

import pytest

from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.index import MemoryIndex


def _make_memory(**overrides) -> Memory:
    """Build a Memory with sensible defaults for testing."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="mem_test1234",
        agent="prime",
        type=MemoryType.IDENTITY,
        tags=["python", "preferences"],
        content="User prefers explicit error handling.",
        confidence=0.8,
        version=1,
        created=now,
        updated=now,
        accessed=now,
    )
    defaults.update(overrides)
    return Memory(**defaults)


@pytest.fixture
async def index():
    """In-memory SQLite index -- no filesystem involved."""
    idx = MemoryIndex(":memory:")
    await idx.initialize()
    yield idx
    await idx.close()


class TestInitialize:
    async def test_creates_table(self):
        idx = MemoryIndex(":memory:")
        await idx.initialize()
        row = await idx.get("nonexistent")
        assert row is None
        await idx.close()


class TestUpsert:
    async def test_insert_new_entry(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path/mem_test1234.md")
        row = await index.get("mem_test1234")
        assert row is not None
        assert row["agent"] == "prime"
        assert row["type"] == "identity"
        assert row["confidence"] == 0.8

    async def test_update_existing_entry(self, index):
        mem = _make_memory(confidence=0.5)
        await index.upsert(mem, "/fake/path.md")
        mem_updated = _make_memory(confidence=0.9)
        await index.upsert(mem_updated, "/fake/path.md")
        row = await index.get("mem_test1234")
        assert row["confidence"] == 0.9


class TestGet:
    async def test_get_existing(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        row = await index.get("mem_test1234")
        assert row is not None
        assert row["id"] == "mem_test1234"
        assert row["file_path"] == "/fake/path.md"

    async def test_get_nonexistent_returns_none(self, index):
        row = await index.get("mem_nonexistent")
        assert row is None


class TestSearch:
    async def test_search_by_tags(self, index):
        mem = _make_memory(tags=["python", "errors"])
        await index.upsert(mem, "/fake/path.md")
        results = await index.search(tags=["python"])
        assert len(results) == 1
        assert results[0]["id"] == "mem_test1234"

    async def test_search_by_agent(self, index):
        mem1 = _make_memory(id="mem_11111111", agent="prime")
        mem2 = _make_memory(id="mem_22222222", agent="code-review")
        await index.upsert(mem1, "/fake/1.md")
        await index.upsert(mem2, "/fake/2.md")
        results = await index.search(agent="prime")
        assert len(results) == 1
        assert results[0]["id"] == "mem_11111111"

    async def test_search_by_type(self, index):
        mem1 = _make_memory(id="mem_11111111", type=MemoryType.IDENTITY)
        mem2 = _make_memory(id="mem_22222222", type=MemoryType.LEARNING)
        await index.upsert(mem1, "/fake/1.md")
        await index.upsert(mem2, "/fake/2.md")
        results = await index.search(memory_type="identity")
        assert len(results) == 1
        assert results[0]["id"] == "mem_11111111"

    async def test_search_combined_filters(self, index):
        mem1 = _make_memory(
            id="mem_11111111", agent="prime",
            type=MemoryType.IDENTITY, tags=["python"],
        )
        mem2 = _make_memory(
            id="mem_22222222", agent="prime",
            type=MemoryType.LEARNING, tags=["python"],
        )
        mem3 = _make_memory(
            id="mem_33333333", agent="code-review",
            type=MemoryType.IDENTITY, tags=["python"],
        )
        await index.upsert(mem1, "/fake/1.md")
        await index.upsert(mem2, "/fake/2.md")
        await index.upsert(mem3, "/fake/3.md")
        results = await index.search(
            tags=["python"], agent="prime", memory_type="identity",
        )
        assert len(results) == 1
        assert results[0]["id"] == "mem_11111111"

    async def test_search_excludes_archived_by_default(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        await index._db.execute(
            "UPDATE memory_index SET is_archived = 1 WHERE id = ?",
            ("mem_test1234",),
        )
        await index._db.commit()
        results = await index.search()
        assert len(results) == 0

    async def test_search_includes_archived_when_requested(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        await index._db.execute(
            "UPDATE memory_index SET is_archived = 1 WHERE id = ?",
            ("mem_test1234",),
        )
        await index._db.commit()
        results = await index.search(include_archived=True)
        assert len(results) == 1

    async def test_search_scores_by_decay(self, index):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)
        mem_recent = _make_memory(id="mem_recent11", accessed=now)
        mem_old = _make_memory(id="mem_old11111", accessed=old)
        await index.upsert(mem_recent, "/fake/recent.md")
        await index.upsert(mem_old, "/fake/old.md")
        results = await index.search()
        assert results[0]["id"] == "mem_recent11"
        assert results[1]["id"] == "mem_old11111"

    async def test_ranking_invariant_recent_high_confidence_wins(self, index):
        """Core invariant: a recently accessed, high-confidence, tag-matching
        memory always outranks a stale, low-confidence one."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)

        good = _make_memory(
            id="mem_good1111",
            tags=["python", "testing"],
            confidence=0.9,
            accessed=now,
            access_count=10,
        )
        stale = _make_memory(
            id="mem_stale111",
            tags=["python", "testing"],
            confidence=0.2,
            accessed=old,
            access_count=1,
        )
        await index.upsert(good, "/fake/good.md")
        await index.upsert(stale, "/fake/stale.md")

        results = await index.search(tags=["python"])
        assert len(results) == 2
        assert results[0]["id"] == "mem_good1111"
        assert results[1]["id"] == "mem_stale111"
        assert results[0]["_score"] > results[1]["_score"] * 2

    async def test_search_respects_decay_half_life(self, index):
        """A shorter half-life penalizes old memories more aggressively."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=30)
        mem = _make_memory(id="mem_decay1111", accessed=old, confidence=0.8)
        await index.upsert(mem, "/fake/decay.md")

        results_default = await index.search(decay_half_life_days=30)
        results_short = await index.search(decay_half_life_days=7)

        assert results_default[0]["_score"] > results_short[0]["_score"]

    async def test_search_respects_limit(self, index):
        for i in range(5):
            mem = _make_memory(id=f"mem_{i:08x}", tags=["test"])
            await index.upsert(mem, f"/fake/{i}.md")
        results = await index.search(limit=2)
        assert len(results) == 2

    async def test_search_no_filters_returns_all_active(self, index):
        for i in range(3):
            mem = _make_memory(id=f"mem_{i:08x}")
            await index.upsert(mem, f"/fake/{i}.md")
        results = await index.search()
        assert len(results) == 3

    async def test_search_tags_no_overlap_returns_empty(self, index):
        mem = _make_memory(tags=["python", "errors"])
        await index.upsert(mem, "/fake/path.md")
        results = await index.search(tags=["javascript"])
        assert len(results) == 0


class TestTouch:
    async def test_touch_updates_access_count(self, index):
        mem = _make_memory(access_count=5)
        await index.upsert(mem, "/fake/path.md")
        await index.touch("mem_test1234")
        row = await index.get("mem_test1234")
        assert row["access_count"] == 6

    async def test_touch_updates_accessed_at(self, index):
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mem = _make_memory(accessed=old_time)
        await index.upsert(mem, "/fake/path.md")
        await index.touch("mem_test1234")
        row = await index.get("mem_test1234")
        accessed = datetime.fromisoformat(row["accessed_at"])
        assert accessed > old_time


class TestRemove:
    async def test_remove_deletes_entry(self, index):
        mem = _make_memory()
        await index.upsert(mem, "/fake/path.md")
        await index.remove("mem_test1234")
        row = await index.get("mem_test1234")
        assert row is None
