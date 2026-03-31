"""Unit tests for MemoryStorage -- filesystem only, no SQLite."""

from datetime import datetime, timezone

import pytest

from signalagent.core.errors import MemoryStoreError
from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.storage import MemoryStorage


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


class TestResolvePath:
    def test_shared_memory_routes_to_shared_dir(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(type=MemoryType.SHARED, agent="prime")
        path = storage.resolve_path(mem)
        assert path == tmp_path / "shared" / "mem_test1234.md"

    def test_shared_type_ignores_agent_name(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(type=MemoryType.SHARED, agent="code-review")
        path = storage.resolve_path(mem)
        assert path == tmp_path / "shared" / "mem_test1234.md"

    def test_prime_memory_routes_to_prime_type_dir(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(agent="prime", type=MemoryType.IDENTITY)
        path = storage.resolve_path(mem)
        assert path == tmp_path / "prime" / "identity" / "mem_test1234.md"

    def test_micro_memory_routes_to_micro_agent_type_dir(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(agent="code-review", type=MemoryType.LEARNING)
        path = storage.resolve_path(mem)
        assert path == tmp_path / "micro" / "code-review" / "learning" / "mem_test1234.md"


class TestWriteAndRead:
    def test_write_creates_file(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory()
        path = storage.write(mem)
        assert path.exists()
        assert path.suffix == ".md"

    def test_write_creates_parent_dirs(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(agent="code-review", type=MemoryType.LEARNING)
        path = storage.write(mem)
        assert path.parent.is_dir()

    def test_roundtrip_preserves_all_fields(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(
            changelog=["v1: Created (2026-03-31, confidence: 0.8)"],
            supersedes=["mem_old00001"],
        )
        path = storage.write(mem)
        loaded = storage.read(path)
        assert loaded.id == mem.id
        assert loaded.agent == mem.agent
        assert loaded.type == mem.type
        assert loaded.tags == mem.tags
        assert loaded.content == mem.content
        assert loaded.confidence == mem.confidence
        assert loaded.version == mem.version
        assert loaded.access_count == mem.access_count
        assert loaded.changelog == mem.changelog
        assert loaded.supersedes == mem.supersedes
        assert loaded.superseded_by == mem.superseded_by
        assert loaded.consolidated_from == mem.consolidated_from

    def test_write_overwrites_existing(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory(content="version 1")
        storage.write(mem)
        mem_v2 = _make_memory(content="version 2")
        path = storage.write(mem_v2)
        loaded = storage.read(path)
        assert loaded.content == "version 2"

    def test_read_nonexistent_raises(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        with pytest.raises(MemoryStoreError, match="not found"):
            storage.read(tmp_path / "nonexistent.md")

    def test_read_invalid_format_raises(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("no frontmatter here")
        with pytest.raises(MemoryStoreError, match="Invalid"):
            storage.read(bad_file)


class TestDelete:
    def test_delete_removes_file(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory()
        path = storage.write(mem)
        assert path.exists()
        storage.delete(path)
        assert not path.exists()

    def test_delete_nonexistent_is_noop(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        storage.delete(tmp_path / "nonexistent.md")  # should not raise


class TestScanAllFiles:
    def test_scan_returns_all_memories(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem1 = _make_memory(id="mem_aaaaaaaa", agent="prime")
        mem2 = _make_memory(id="mem_bbbbbbbb", agent="code-review", type=MemoryType.LEARNING)
        storage.write(mem1)
        storage.write(mem2)
        results = storage.scan_all_files()
        assert len(results) == 2
        ids = {mem.id for _, mem in results}
        assert ids == {"mem_aaaaaaaa", "mem_bbbbbbbb"}

    def test_scan_skips_invalid_files(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        mem = _make_memory()
        storage.write(mem)
        # Add an invalid .md file
        bad_file = tmp_path / "shared" / "bad.md"
        bad_file.parent.mkdir(parents=True, exist_ok=True)
        bad_file.write_text("no frontmatter here")
        results = storage.scan_all_files()
        assert len(results) == 1

    def test_scan_empty_directory(self, tmp_path):
        storage = MemoryStorage(tmp_path)
        results = storage.scan_all_files()
        assert len(results) == 0
