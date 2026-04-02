"""Tests for JSONL worktree manifest."""
from datetime import datetime, timezone
from pathlib import Path

from signalagent.worktrees.manifest import WorktreeManifest
from signalagent.worktrees.models import WorktreeRecord


def _make_record(
    id: str = "wt_abc12345",
    status: str = "pending",
    agent_name: str = "coder",
) -> WorktreeRecord:
    return WorktreeRecord(
        id=id,
        worktree_path=Path("/tmp/wt"),
        workspace_root=Path("/project"),
        agent_name=agent_name,
        created=datetime(2026, 4, 2, tzinfo=timezone.utc),
        status=status,
        is_git=True,
        branch_name=f"signal/worktree/{agent_name}_{id}",
    )


class TestWorktreeManifest:
    def test_append_and_load(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record())
        loaded = manifest.load()
        assert "wt_abc12345" in loaded
        assert loaded["wt_abc12345"].status == "pending"

    def test_empty_manifest(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        assert manifest.load() == {}

    def test_last_record_wins(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record(id="wt_001", status="pending"))
        manifest.append(_make_record(id="wt_001", status="merged"))
        loaded = manifest.load()
        assert loaded["wt_001"].status == "merged"

    def test_skip_malformed_lines(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record())
        with open(manifest._path, "a") as f:
            f.write("this is not json\n")
        loaded = manifest.load()
        assert len(loaded) == 1
        assert "wt_abc12345" in loaded

    def test_list_pending(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record(id="wt_001", status="pending"))
        manifest.append(_make_record(id="wt_002", status="merged"))
        manifest.append(_make_record(id="wt_003", status="pending"))
        pending = manifest.list_pending()
        assert len(pending) == 2
        ids = {r.id for r in pending}
        assert ids == {"wt_001", "wt_003"}

    def test_list_pending_excludes_superseded(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record(id="wt_001", status="pending"))
        manifest.append(_make_record(id="wt_001", status="discarded"))
        pending = manifest.list_pending()
        assert len(pending) == 0

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        manifest = WorktreeManifest(nested)
        manifest.append(_make_record())
        assert manifest._path.exists()

    def test_get_by_id(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        manifest.append(_make_record(id="wt_001"))
        manifest.append(_make_record(id="wt_002"))
        record = manifest.get("wt_001")
        assert record is not None
        assert record.id == "wt_001"

    def test_get_by_id_not_found(self, tmp_path: Path) -> None:
        manifest = WorktreeManifest(tmp_path)
        assert manifest.get("wt_nonexistent") is None
