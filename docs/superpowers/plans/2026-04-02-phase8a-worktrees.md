# Phase 8a: Worktrees Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add worktree isolation to the agent execution pipeline so file writes go to isolated workspaces, reviewed and merged by the user via CLI.

**Architecture:** WorktreeProxy wraps the HookExecutor chain as the outermost tool executor. Lazy worktree creation on first `file_system` write. Git worktrees when available, directory copy fallback. CLI commands for merge/discard. Review is always explicit.

**Tech Stack:** Python 3.12, Pydantic v2, subprocess (git), shutil, difflib, Typer + Rich (CLI)

---

## File Structure

**New files:**
- `src/signalagent/core/constants.py` -- shared IGNORE_DIRS constant
- `src/signalagent/worktrees/__init__.py` -- package init
- `src/signalagent/worktrees/models.py` -- WorktreeResult, WorktreeRecord
- `src/signalagent/worktrees/manifest.py` -- JSONL manifest reader/writer
- `src/signalagent/worktrees/manager.py` -- filesystem mechanics (git + non-git)
- `src/signalagent/worktrees/proxy.py` -- WorktreeProxy
- `src/signalagent/cli/worktree_cmd.py` -- CLI commands (list, merge, discard)
- `tests/unit/worktrees/__init__.py`
- `tests/unit/worktrees/test_models.py`
- `tests/unit/worktrees/test_manifest.py`
- `tests/unit/worktrees/test_manager.py`
- `tests/unit/worktrees/test_proxy.py`

**Modified files:**
- `src/signalagent/core/protocols.py` -- add WorktreeProxyProtocol
- `src/signalagent/heartbeat/detector.py` -- import IGNORE_DIRS from shared constant
- `src/signalagent/agents/micro.py` -- add worktree_proxy param, take_result() call
- `src/signalagent/runtime/bootstrap.py` -- wire WorktreeProxy per agent
- `src/signalagent/cli/app.py` -- register worktree commands
- `tests/unit/agents/test_micro.py` -- worktree integration tests
- `tests/unit/runtime/test_bootstrap.py` -- worktree wiring tests
- `VERSION` -- 0.9.0 -> 0.10.0
- `CHANGELOG.md` -- add 0.10.0 section
- `docs/dev/roadmap.md` -- split Phase 8, mark 8a Complete

---

### Task 1: Shared Constants and WorktreeProxyProtocol

**Files:**
- Create: `src/signalagent/core/constants.py`
- Modify: `src/signalagent/heartbeat/detector.py:15`
- Modify: `src/signalagent/core/protocols.py:65`
- Create: `tests/unit/core/test_constants.py`

- [ ] **Step 1: Write tests for shared IGNORE_DIRS constant**

```python
# tests/unit/core/test_constants.py
"""Tests for shared constants."""
from signalagent.core.constants import IGNORE_DIRS


class TestIgnoreDirs:
    def test_contains_expected_dirs(self) -> None:
        expected = {".git", "__pycache__", "node_modules", ".signal", ".venv", "venv"}
        assert expected == IGNORE_DIRS

    def test_is_frozenset(self) -> None:
        assert isinstance(IGNORE_DIRS, frozenset)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/core/test_constants.py -v`
Expected: FAIL with ModuleNotFoundError (constants module does not exist)

- [ ] **Step 3: Create constants module**

```python
# src/signalagent/core/constants.py
"""Shared constants used across multiple modules."""

IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", ".signal", ".venv", "venv",
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/core/test_constants.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update detector to import from shared constant**

In `src/signalagent/heartbeat/detector.py`, replace line 15:

```python
# OLD:
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".signal", ".venv", "venv"}

# NEW:
from signalagent.core.constants import IGNORE_DIRS
```

Remove the local definition entirely. The rest of the file is unchanged.

- [ ] **Step 6: Run detector tests to verify nothing breaks**

Run: `.venv/Scripts/python -m pytest tests/unit/heartbeat/test_detector.py -v`
Expected: PASS (all existing detector tests still pass)

- [ ] **Step 7: Write test for WorktreeProxyProtocol**

Append to `tests/unit/core/test_protocols.py`:

```python
from signalagent.core.protocols import WorktreeProxyProtocol


class _FakeWorktreeProxy:
    def take_result(self):
        return None


class TestWorktreeProxyProtocol:
    def test_structural_subtyping(self) -> None:
        proxy = _FakeWorktreeProxy()
        assert isinstance(proxy, WorktreeProxyProtocol)
```

- [ ] **Step 8: Run protocol tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/core/test_protocols.py::TestWorktreeProxyProtocol -v`
Expected: FAIL with ImportError (WorktreeProxyProtocol does not exist)

- [ ] **Step 9: Add WorktreeProxyProtocol to protocols.py**

Append to `src/signalagent/core/protocols.py` after the MemoryReaderProtocol class:

```python
@runtime_checkable
class WorktreeProxyProtocol(Protocol):
    """Protocol for worktree proxy -- agents call take_result() after task completion."""

    def take_result(self) -> Any: ...
```

- [ ] **Step 10: Run all protocol tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/core/test_protocols.py -v`
Expected: PASS (all tests including new TestWorktreeProxyProtocol)

- [ ] **Step 11: Commit**

```bash
git add src/signalagent/core/constants.py src/signalagent/core/protocols.py src/signalagent/heartbeat/detector.py tests/unit/core/test_constants.py tests/unit/core/test_protocols.py
git commit -m "feat: add shared IGNORE_DIRS constant and WorktreeProxyProtocol"
```

---

### Task 2: Worktree Models

**Files:**
- Create: `src/signalagent/worktrees/__init__.py`
- Create: `src/signalagent/worktrees/models.py`
- Create: `tests/unit/worktrees/__init__.py`
- Create: `tests/unit/worktrees/test_models.py`

- [ ] **Step 1: Write tests for WorktreeResult and WorktreeRecord**

```python
# tests/unit/worktrees/__init__.py
```

```python
# tests/unit/worktrees/test_models.py
"""Tests for worktree data models."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signalagent.worktrees.models import WorktreeResult, WorktreeRecord


class TestWorktreeResult:
    def test_construction(self) -> None:
        r = WorktreeResult(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["src/main.py", "src/utils.py"],
            diff="--- a/src/main.py\n+++ b/src/main.py\n",
            agent_name="coder",
            is_git=True,
        )
        assert r.id == "wt_abc12345"
        assert r.changed_files == ["src/main.py", "src/utils.py"]
        assert r.is_git is True
        assert r.agent_name == "coder"

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            WorktreeResult(
                id="wt_abc12345",
                worktree_path=Path("/tmp/wt"),
                workspace_root=Path("/project"),
                changed_files=[],
                diff="",
                agent_name="coder",
                is_git=True,
                surprise="bad",
            )


class TestWorktreeRecord:
    def test_construction(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=True,
            branch_name="signal/worktree/coder_wt_abc12345",
        )
        assert r.status == "pending"
        assert r.branch_name == "signal/worktree/coder_wt_abc12345"

    def test_branch_name_optional(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=False,
        )
        assert r.branch_name is None

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            WorktreeRecord(
                id="wt_abc12345",
                worktree_path=Path("/tmp/wt"),
                workspace_root=Path("/project"),
                agent_name="coder",
                created=datetime(2026, 4, 2, tzinfo=timezone.utc),
                status="pending",
                is_git=True,
                surprise="bad",
            )

    def test_json_roundtrip(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=True,
            branch_name="signal/worktree/coder_wt_abc12345",
        )
        json_str = r.model_dump_json()
        restored = WorktreeRecord.model_validate_json(json_str)
        assert restored.id == r.id
        assert restored.worktree_path == r.worktree_path
        assert restored.created == r.created
        assert restored.branch_name == r.branch_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_models.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create worktrees package and models**

```python
# src/signalagent/worktrees/__init__.py
```

```python
# src/signalagent/worktrees/models.py
"""Data models for worktree isolation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class WorktreeResult(BaseModel):
    """Returned by WorktreeProxy.take_result() when writes occurred."""

    model_config = ConfigDict(extra="forbid")

    id: str
    worktree_path: Path
    workspace_root: Path
    changed_files: list[str]
    diff: str
    agent_name: str
    is_git: bool


class WorktreeRecord(BaseModel):
    """Manifest entry tracking worktree lifecycle."""

    model_config = ConfigDict(extra="forbid")

    id: str
    worktree_path: Path
    workspace_root: Path
    agent_name: str
    created: datetime
    status: str  # "pending" | "merged" | "discarded"
    is_git: bool
    branch_name: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/worktrees/ tests/unit/worktrees/
git commit -m "feat: add WorktreeResult and WorktreeRecord models"
```

---

### Task 3: WorktreeManifest

**Files:**
- Create: `src/signalagent/worktrees/manifest.py`
- Create: `tests/unit/worktrees/test_manifest.py`

- [ ] **Step 1: Write tests for manifest JSONL operations**

```python
# tests/unit/worktrees/test_manifest.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_manifest.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement WorktreeManifest**

```python
# src/signalagent/worktrees/manifest.py
"""JSONL manifest for tracking worktree lifecycle."""
from __future__ import annotations

import logging
from pathlib import Path

from signalagent.worktrees.models import WorktreeRecord

logger = logging.getLogger(__name__)


class WorktreeManifest:
    """Append-only JSONL manifest for worktree records.

    Status updates are appended as new lines. Reader builds a
    dict[id, record] by iterating all lines -- later entries
    overwrite earlier ones for the same ID.
    """

    def __init__(self, worktrees_dir: Path) -> None:
        self._path = worktrees_dir / "manifest.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: WorktreeRecord) -> None:
        """Append a record to the manifest."""
        with open(self._path, "a") as f:
            f.write(record.model_dump_json() + "\n")

    def load(self) -> dict[str, WorktreeRecord]:
        """Load all records. Last entry per ID wins."""
        if not self._path.exists():
            return {}
        records: dict[str, WorktreeRecord] = {}
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = WorktreeRecord.model_validate_json(line)
                records[record.id] = record
            except Exception:
                logger.warning("Skipping malformed manifest line: %s", line[:80])
        return records

    def get(self, worktree_id: str) -> WorktreeRecord | None:
        """Get the resolved record for a worktree ID."""
        return self.load().get(worktree_id)

    def list_pending(self) -> list[WorktreeRecord]:
        """Return pending worktrees, newest first."""
        records = self.load()
        return sorted(
            [r for r in records.values() if r.status == "pending"],
            key=lambda r: r.created,
            reverse=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_manifest.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/worktrees/manifest.py tests/unit/worktrees/test_manifest.py
git commit -m "feat: add WorktreeManifest with JSONL persistence"
```

---

### Task 4: WorktreeManager -- Git Mode

**Files:**
- Create: `src/signalagent/worktrees/manager.py`
- Create: `tests/unit/worktrees/test_manager.py`

- [ ] **Step 1: Write tests for git-mode operations**

```python
# tests/unit/worktrees/test_manager.py
"""Tests for WorktreeManager."""
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, MagicMock

import pytest

from signalagent.worktrees.manager import WorktreeManager


class TestGitDetection:
    def test_detects_git_repo(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.is_git is True

    def test_detects_non_git(self, tmp_path: Path) -> None:
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.is_git is False


class TestGitCreate:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_creates_git_worktree(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(args=[], returncode=0)
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        result = mgr.create("coder_wt_abc123")
        expected_target = tmp_path / "data" / "worktrees" / "coder_wt_abc123"
        assert result == expected_target
        mock_sub.run.assert_called_once()
        args = mock_sub.run.call_args
        assert "worktree" in args[0][0]
        assert "-b" in args[0][0]
        assert "signal/worktree/coder_wt_abc123" in args[0][0]


class TestGitDiff:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_returns_diff_output(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0,
            stdout="--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        diff = mgr.diff(tmp_path / "data" / "worktrees" / "wt1")
        assert "--- a/file.py" in diff
        assert "+new" in diff


class TestGitChangedFiles:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_returns_sorted_files(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0,
            stdout="src/utils.py\nsrc/main.py\n",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        files = mgr.changed_files(tmp_path / "wt")
        assert files == ["src/main.py", "src/utils.py"]

    @patch("signalagent.worktrees.manager.subprocess")
    def test_empty_when_no_changes(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.changed_files(tmp_path / "wt") == []


class TestMerge:
    def test_copies_changed_files(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "existing.py").write_text("old content")

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "existing.py").write_text("new content")
        (worktree / "new_file.py").write_text("brand new")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        # Use non-git mode for merge test (merge is file-copy regardless)
        mgr._is_git = False
        mgr.merge(worktree)
        assert (workspace / "existing.py").read_text() == "new content"
        assert (workspace / "new_file.py").read_text() == "brand new"

    def test_deletes_removed_files(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "to_delete.py").write_text("will be removed")

        # Use create() so the worktree starts as a proper copy of workspace
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("del_test")
        # Agent deletes the file in the worktree
        (target / "to_delete.py").unlink()

        mgr.merge(target)
        assert not (workspace / "to_delete.py").exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "deep" / "nested").mkdir(parents=True)
        (worktree / "deep" / "nested" / "file.py").write_text("content")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        mgr._is_git = False
        mgr.merge(worktree)
        assert (workspace / "deep" / "nested" / "file.py").read_text() == "content"


class TestCleanup:
    def test_removes_directory(self, tmp_path: Path) -> None:
        wt_dir = tmp_path / "worktree"
        wt_dir.mkdir()
        (wt_dir / "file.py").write_text("content")
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(wt_dir)
        assert not wt_dir.exists()

    @patch("signalagent.worktrees.manager.subprocess")
    def test_prunes_git_worktree(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        wt_dir = tmp_path / "worktree"
        wt_dir.mkdir()
        mock_sub.run.return_value = CompletedProcess(args=[], returncode=0)
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(wt_dir, branch_name="signal/worktree/test")
        calls = mock_sub.run.call_args_list
        assert len(calls) == 2
        assert "prune" in calls[0][0][0]
        assert "-D" in calls[1][0][0]
        assert "signal/worktree/test" in calls[1][0][0]

    def test_noop_if_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(missing)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_manager.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement WorktreeManager**

```python
# src/signalagent/worktrees/manager.py
"""WorktreeManager -- filesystem mechanics for worktree creation and management."""
from __future__ import annotations

import difflib
import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path

from signalagent.core.constants import IGNORE_DIRS

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Creates and destroys git worktrees and directory copies.

    Pure filesystem mechanics. No awareness of agents, tasks, or the
    message bus. Stateless -- state lives in the manifest.
    """

    def __init__(self, instance_dir: Path, workspace_root: Path) -> None:
        self._instance_dir = instance_dir
        self._workspace_root = workspace_root
        self._worktrees_dir = instance_dir / "data" / "worktrees"
        self._is_git: bool = (workspace_root / ".git").is_dir()

    @property
    def is_git(self) -> bool:
        return self._is_git

    def create(self, name: str) -> Path:
        """Create a worktree. Returns the worktree path."""
        self._worktrees_dir.mkdir(parents=True, exist_ok=True)
        target = self._worktrees_dir / name
        if self._is_git:
            return self._create_git(name, target)
        return self._create_copy(target)

    def diff(self, worktree_path: Path) -> str:
        """Return unified diff of changes in the worktree."""
        if self._is_git:
            return self._diff_git(worktree_path)
        return self._diff_copy(worktree_path)

    def changed_files(self, worktree_path: Path) -> list[str]:
        """Return sorted list of changed file paths (relative)."""
        if self._is_git:
            return self._changed_files_git(worktree_path)
        return self._changed_files_copy(worktree_path)

    def merge(self, worktree_path: Path) -> None:
        """Copy changed files from worktree to workspace."""
        files = self.changed_files(worktree_path)
        for rel in files:
            src = worktree_path / rel
            dst = self._workspace_root / rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            elif dst.exists():
                dst.unlink()

    def cleanup(self, worktree_path: Path, branch_name: str | None = None) -> None:
        """Remove worktree directory and prune git references."""
        if worktree_path.exists():
            shutil.rmtree(worktree_path)
        if self._is_git:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(self._workspace_root),
                capture_output=True, text=True,
            )
            if branch_name:
                subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=str(self._workspace_root),
                    capture_output=True, text=True,
                )

    # -- Git mode -------------------------------------------------------

    def _create_git(self, name: str, target: Path) -> Path:
        branch = f"signal/worktree/{name}"
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(target), "HEAD"],
            cwd=str(self._workspace_root),
            capture_output=True, text=True, check=True,
        )
        return target

    def _diff_git(self, worktree_path: Path) -> str:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(worktree_path),
            capture_output=True, text=True,
        )
        return result.stdout

    def _changed_files_git(self, worktree_path: Path) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(worktree_path),
            capture_output=True, text=True,
        )
        return sorted(line for line in result.stdout.splitlines() if line.strip())

    # -- Non-git mode ---------------------------------------------------

    def _create_copy(self, target: Path) -> Path:
        shutil.copytree(
            self._workspace_root, target,
            ignore=shutil.ignore_patterns(*IGNORE_DIRS),
        )
        return target

    def _diff_copy(self, worktree_path: Path) -> str:
        changed = self._changed_files_copy(worktree_path)
        parts: list[str] = []
        for rel in changed:
            ws_file = self._workspace_root / rel
            wt_file = worktree_path / rel
            ws_lines = (
                ws_file.read_text().splitlines(keepends=True) if ws_file.exists() else []
            )
            wt_lines = (
                wt_file.read_text().splitlines(keepends=True) if wt_file.exists() else []
            )
            diff_lines = difflib.unified_diff(
                ws_lines, wt_lines,
                fromfile=f"a/{rel}", tofile=f"b/{rel}",
            )
            parts.extend(diff_lines)
        return "".join(parts)

    def _changed_files_copy(self, worktree_path: Path) -> list[str]:
        ws_files = self._walk_files(self._workspace_root)
        wt_files = self._walk_files(worktree_path)
        changed: list[str] = []
        for rel in sorted(ws_files | wt_files):
            ws_file = self._workspace_root / rel
            wt_file = worktree_path / rel
            if not ws_file.exists() or not wt_file.exists():
                changed.append(rel)
            elif self._file_hash(ws_file) != self._file_hash(wt_file):
                changed.append(rel)
        return changed

    def _walk_files(self, root: Path) -> set[str]:
        """Walk directory, return relative paths, skip IGNORE_DIRS."""
        result: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for f in filenames:
                full = Path(dirpath) / f
                result.add(str(full.relative_to(root)))
            dirnames.sort()
        return result

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_manager.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/worktrees/manager.py tests/unit/worktrees/test_manager.py
git commit -m "feat: add WorktreeManager with git and non-git modes"
```

---

### Task 5: WorktreeManager -- Non-Git Fallback Tests

**Files:**
- Modify: `tests/unit/worktrees/test_manager.py`

This task adds integration-style tests for the non-git (directory copy) path using real filesystems.

- [ ] **Step 1: Add non-git tests**

Append to `tests/unit/worktrees/test_manager.py`:

```python
class TestNonGitCreate:
    def test_copies_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("hello")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        assert mgr.is_git is False
        target = mgr.create("test_wt")
        assert target.exists()
        assert (target / "src" / "main.py").read_text() == "hello"

    def test_ignores_dirs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "__pycache__").mkdir()
        (workspace / "__pycache__" / "cache.pyc").write_bytes(b"bytes")
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("code")
        (workspace / "node_modules").mkdir()
        (workspace / "node_modules" / "big.js").write_text("js")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert (target / "src" / "main.py").exists()
        assert not (target / "__pycache__").exists()
        assert not (target / "node_modules").exists()


class TestNonGitChangedFiles:
    def test_detects_modified_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "file.py").write_text("original")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "file.py").write_text("modified")
        changed = mgr.changed_files(target)
        assert "file.py" in changed

    def test_detects_new_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "old.py").write_text("content")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "new.py").write_text("added")
        changed = mgr.changed_files(target)
        assert "new.py" in changed

    def test_detects_deleted_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "gone.py").write_text("will be deleted")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "gone.py").unlink()
        changed = mgr.changed_files(target)
        assert "gone.py" in changed

    def test_unchanged_returns_empty(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "same.py").write_text("untouched")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert mgr.changed_files(target) == []


class TestNonGitDiff:
    def test_produces_unified_diff(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "file.py").write_text("old line\n")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "file.py").write_text("new line\n")
        diff = mgr.diff(target)
        assert "--- a/file.py" in diff
        assert "+++ b/file.py" in diff
        assert "-old line" in diff
        assert "+new line" in diff

    def test_empty_diff_when_unchanged(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "same.py").write_text("untouched\n")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert mgr.diff(target) == ""
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_manager.py -v`
Expected: PASS (all tests including new non-git tests)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/worktrees/test_manager.py
git commit -m "test: add non-git fallback tests for WorktreeManager"
```

---

### Task 6: WorktreeProxy

**Files:**
- Create: `src/signalagent/worktrees/proxy.py`
- Create: `tests/unit/worktrees/test_proxy.py`

- [ ] **Step 1: Write tests for WorktreeProxy**

```python
# tests/unit/worktrees/test_proxy.py
"""Tests for WorktreeProxy."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalagent.core.models import ToolResult
from signalagent.core.protocols import WorktreeProxyProtocol
from signalagent.worktrees.proxy import WorktreeProxy


@pytest.fixture
def mock_inner() -> AsyncMock:
    """Mock inner executor (HookExecutor chain)."""
    inner = AsyncMock()
    inner.return_value = ToolResult(output="inner result")
    return inner


@pytest.fixture
def mock_hook_registry() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.is_git = True
    mgr.create.return_value = Path("/tmp/wt/test_wt")
    mgr.changed_files.return_value = ["src/main.py"]
    mgr.diff.return_value = "--- a/src/main.py\n+++ b/src/main.py\n"
    return mgr


@pytest.fixture
def mock_manifest() -> MagicMock:
    return MagicMock()


@pytest.fixture
def proxy(
    mock_inner: AsyncMock,
    mock_hook_registry: MagicMock,
    mock_manager: MagicMock,
    mock_manifest: MagicMock,
    tmp_path: Path,
) -> WorktreeProxy:
    return WorktreeProxy(
        inner=mock_inner,
        hook_registry=mock_hook_registry,
        worktree_manager=mock_manager,
        manifest=mock_manifest,
        workspace_root=tmp_path / "workspace",
        instance_dir=tmp_path,
        agent_name="coder",
    )


class TestPassthroughMode:
    @pytest.mark.asyncio
    async def test_non_file_system_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        result = await proxy("bash", {"command": "ls"})
        mock_inner.assert_called_once_with("bash", {"command": "ls"})
        assert result.output == "inner result"

    @pytest.mark.asyncio
    async def test_file_system_read_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        result = await proxy("file_system", {"operation": "read", "path": "src/main.py"})
        mock_inner.assert_called_once_with(
            "file_system", {"operation": "read", "path": "src/main.py"},
        )

    @pytest.mark.asyncio
    async def test_file_system_list_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        await proxy("file_system", {"operation": "list", "path": "."})
        mock_inner.assert_called_once()


class TestIsolatedMode:
    @pytest.mark.asyncio
    async def test_first_write_creates_worktree(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        # Mock the worktree FileSystemTool execution
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="Written: src/main.py")
            await proxy("file_system", {"operation": "write", "path": "src/main.py", "content": "hello"})
        mock_manager.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_after_write_goes_to_worktree(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            # First write triggers isolation
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
            # Subsequent read goes to worktree, not inner
            await proxy("file_system", {"operation": "read", "path": "f.py"})
        assert mock_exec.call_count == 2
        # Inner should NOT be called for file_system after isolation
        for call in mock_inner.call_args_list:
            assert call[0][0] != "file_system"

    @pytest.mark.asyncio
    async def test_non_file_system_still_passes_through_in_isolated(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
        # Non-file_system should still go through inner
        await proxy("bash", {"command": "ls"})
        mock_inner.assert_called_with("bash", {"command": "ls"})


class TestHooksInIsolatedMode:
    @pytest.mark.asyncio
    async def test_before_and_after_hooks_fire(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        before_calls: list[tuple] = []
        after_calls: list[tuple] = []

        class FakeHook:
            name = "test_hook"
            async def before_tool_call(self, tool_name, arguments):
                before_calls.append((tool_name, arguments))
                return None
            async def after_tool_call(self, tool_name, arguments, result, blocked):
                after_calls.append((tool_name, arguments, blocked))

        proxy._hook_registry.get_all.return_value = [FakeHook()]

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="Written: f.py")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        assert len(before_calls) == 1
        assert before_calls[0][0] == "file_system"
        assert len(after_calls) == 1
        assert after_calls[0][2] is False  # blocked=False

    @pytest.mark.asyncio
    async def test_hook_can_block(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")

        class BlockingHook:
            name = "blocker"
            async def before_tool_call(self, tool_name, arguments):
                return ToolResult(output="", error="Blocked by policy")
            async def after_tool_call(self, tool_name, arguments, result, blocked):
                pass

        proxy._hook_registry.get_all.return_value = [BlockingHook()]

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            # Trigger isolation first with no hooks
            proxy._hook_registry.get_all.return_value = []
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
            # Now add blocking hook
            proxy._hook_registry.get_all.return_value = [BlockingHook()]
            result = await proxy("file_system", {"operation": "write", "path": "g.py", "content": "y"})

        assert result.error == "Blocked by policy"


class TestTakeResult:
    @pytest.mark.asyncio
    async def test_returns_result_after_writes(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        result = proxy.take_result()
        assert result is not None
        assert result.agent_name == "coder"
        assert result.changed_files == ["src/main.py"]

    def test_returns_none_without_writes(self, proxy: WorktreeProxy) -> None:
        assert proxy.take_result() is None

    @pytest.mark.asyncio
    async def test_resets_after_take(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        proxy.take_result()
        assert proxy.take_result() is None

    def test_satisfies_protocol(self) -> None:
        assert issubclass(WorktreeProxy, WorktreeProxyProtocol)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_proxy.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement WorktreeProxy**

```python
# src/signalagent/worktrees/proxy.py
"""WorktreeProxy -- per-agent tool executor wrapper for worktree isolation."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.models import ToolResult
from signalagent.core.protocols import ToolExecutor
from signalagent.hooks.registry import HookRegistry
from signalagent.tools.builtins.file_system import FileSystemTool
from signalagent.worktrees.manager import WorktreeManager
from signalagent.worktrees.manifest import WorktreeManifest
from signalagent.worktrees.models import WorktreeRecord, WorktreeResult

logger = logging.getLogger(__name__)


class WorktreeProxy:
    """Per-agent tool executor that isolates file writes to a worktree.

    State machine: PASSTHROUGH -> ISOLATED (on first file_system write).
    Resets to PASSTHROUGH after take_result() is called.

    The proxy wraps the HookExecutor chain (outermost executor layer).
    Non-file_system calls always pass through. In ISOLATED mode,
    file_system calls go to a worktree-rooted FileSystemTool and hooks
    are called directly.
    """

    def __init__(
        self,
        inner: ToolExecutor,
        hook_registry: HookRegistry,
        worktree_manager: WorktreeManager,
        manifest: WorktreeManifest,
        workspace_root: Path,
        instance_dir: Path,
        agent_name: str,
    ) -> None:
        self._inner = inner
        self._hook_registry = hook_registry
        self._manager = worktree_manager
        self._manifest = manifest
        self._workspace_root = workspace_root
        self._instance_dir = instance_dir
        self._agent_name = agent_name

        # Per-task state -- reset by take_result()
        self._worktree_path: Path | None = None
        self._worktree_tool: FileSystemTool | None = None
        self._worktree_id: str | None = None
        self._is_isolated: bool = False

    async def __call__(self, tool_name: str, arguments: dict) -> ToolResult:
        # Non-file_system always passes through
        if tool_name != "file_system":
            return await self._inner(tool_name, arguments)

        operation = arguments.get("operation", "")

        # Lazy worktree creation on first write
        if operation == "write" and not self._is_isolated:
            self._create_worktree()

        if self._is_isolated:
            return await self._execute_isolated(tool_name, arguments)

        # PASSTHROUGH: use inner chain
        return await self._inner(tool_name, arguments)

    def _create_worktree(self) -> None:
        self._worktree_id = f"wt_{secrets.token_hex(4)}"
        name = f"{self._agent_name}_{self._worktree_id}"
        self._worktree_path = self._manager.create(name)
        self._worktree_tool = FileSystemTool(root=self._worktree_path)
        self._is_isolated = True

        record = WorktreeRecord(
            id=self._worktree_id,
            worktree_path=self._worktree_path,
            workspace_root=self._workspace_root,
            agent_name=self._agent_name,
            created=datetime.now(timezone.utc),
            status="pending",
            is_git=self._manager.is_git,
            branch_name=(
                f"signal/worktree/{name}" if self._manager.is_git else None
            ),
        )
        self._manifest.append(record)

    async def _execute_isolated(self, tool_name: str, arguments: dict) -> ToolResult:
        """Execute file_system call against worktree, calling hooks directly."""
        return await self._execute_in_worktree(tool_name, arguments)

    async def _execute_in_worktree(self, tool_name: str, arguments: dict) -> ToolResult:
        """Run hooks manually, then execute against worktree-rooted tool."""
        hooks = self._hook_registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(tool_name, arguments)
            except Exception as e:
                logger.warning(
                    "Hook '%s' before_tool_call raised (fail open): %s",
                    hook.name, e,
                )
                continue
            if before_result is not None:
                result = before_result
                blocked = True
                break

        # Execute against worktree tool if not blocked
        if not blocked:
            assert self._worktree_tool is not None
            try:
                result = await self._worktree_tool.execute(**arguments)
            except Exception as e:
                result = ToolResult(output="", error=str(e))

        assert result is not None

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(tool_name, arguments, result, blocked)
            except Exception as e:
                logger.warning("Hook '%s' after_tool_call raised: %s", hook.name, e)

        return result

    def take_result(self) -> WorktreeResult | None:
        """Return WorktreeResult if writes occurred, None otherwise.
        Resets state to PASSTHROUGH for the next task."""
        if not self._is_isolated or self._worktree_path is None:
            return None

        result = WorktreeResult(
            id=self._worktree_id,
            worktree_path=self._worktree_path,
            workspace_root=self._workspace_root,
            changed_files=self._manager.changed_files(self._worktree_path),
            diff=self._manager.diff(self._worktree_path),
            agent_name=self._agent_name,
            is_git=self._manager.is_git,
        )

        # Reset for next task
        self._worktree_path = None
        self._worktree_tool = None
        self._worktree_id = None
        self._is_isolated = False

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/worktrees/test_proxy.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/worktrees/proxy.py tests/unit/worktrees/test_proxy.py
git commit -m "feat: add WorktreeProxy with lazy creation and hook preservation"
```

---

### Task 7: MicroAgent Integration

**Files:**
- Modify: `src/signalagent/agents/micro.py`
- Modify: `tests/unit/agents/test_micro.py`

- [ ] **Step 1: Write tests for worktree integration in MicroAgent**

Append to `tests/unit/agents/test_micro.py`:

```python
from signalagent.worktrees.models import WorktreeResult


class _FakeWorktreeProxy:
    """Minimal fake satisfying WorktreeProxyProtocol."""

    def __init__(self, result: WorktreeResult | None = None) -> None:
        self._result = result

    def take_result(self) -> WorktreeResult | None:
        r = self._result
        self._result = None
        return r


class TestMicroAgentWorktree:
    @pytest.mark.asyncio
    async def test_appends_review_instructions(self) -> None:
        wt_result = WorktreeResult(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["src/main.py", "src/utils.py"],
            diff="diff output",
            agent_name="coder",
            is_git=True,
        )
        proxy = _FakeWorktreeProxy(result=wt_result)
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Task complete.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        # Register and send message
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix the bug",
        )
        response = await agent._handle(msg)
        assert "signal worktree merge wt_abc12345" in response.content
        assert "signal worktree discard wt_abc12345" in response.content
        assert "src/main.py" in response.content

    @pytest.mark.asyncio
    async def test_no_review_without_writes(self) -> None:
        proxy = _FakeWorktreeProxy(result=None)
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Analysis complete.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="analyzer", skill="analysis"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="analyzer", content="analyze this",
        )
        response = await agent._handle(msg)
        assert "worktree" not in response.content.lower()
        assert response.content == "Analysis complete."

    @pytest.mark.asyncio
    async def test_no_review_without_proxy(self) -> None:
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Done.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="basic", skill="general"),
            runner=runner,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="basic", content="do something",
        )
        response = await agent._handle(msg)
        assert response.content == "Done."

    @pytest.mark.asyncio
    async def test_preserves_worktree_on_runner_error(self) -> None:
        wt_result = WorktreeResult(
            id="wt_err12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["partial.py"],
            diff="partial diff",
            agent_name="coder",
            is_git=True,
        )
        proxy = _FakeWorktreeProxy(result=wt_result)
        runner = AsyncMock()
        runner.run.side_effect = RuntimeError("AI layer failed")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix it",
        )
        response = await agent._handle(msg)
        assert "signal worktree merge wt_err12345" in response.content
        assert "partial.py" in response.content
        assert "failed" in response.content.lower()

    @pytest.mark.asyncio
    async def test_reraises_without_worktree_state(self) -> None:
        proxy = _FakeWorktreeProxy(result=None)
        runner = AsyncMock()
        runner.run.side_effect = RuntimeError("AI layer failed")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix it",
        )
        with pytest.raises(RuntimeError, match="AI layer failed"):
            await agent._handle(msg)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/agents/test_micro.py::TestMicroAgentWorktree -v`
Expected: FAIL (MicroAgent does not accept worktree_proxy parameter)

- [ ] **Step 3: Update MicroAgent to accept and use worktree proxy**

Replace the full content of `src/signalagent/agents/micro.py`:

```python
"""MicroAgent -- skill-based specialist agent."""
from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import (
    MemoryReaderProtocol,
    RunnerProtocol,
    WorktreeProxyProtocol,
)
from signalagent.core.types import AgentType, MessageType
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT

logger = logging.getLogger(__name__)


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.
    Delegates all LLM interaction to an injected RunnerProtocol."""

    def __init__(
        self,
        config: MicroAgentConfig,
        runner: RunnerProtocol,
        memory_reader: MemoryReaderProtocol | None = None,
        model: str = "",
        worktree_proxy: WorktreeProxyProtocol | None = None,
    ) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._memory_reader = memory_reader
        self._model = model
        self._worktree_proxy = worktree_proxy

    @property
    def skill(self) -> str:
        return self._config.skill

    def _build_identity(self) -> str:
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        memories = []
        if self._memory_reader:
            try:
                memories = await self._memory_reader.search(
                    agent=self._config.name, limit=DEFAULT_MEMORY_LIMIT,
                )
            except Exception:
                logger.warning("Memory retrieval failed, proceeding without context")

        if memories and self._model:
            system_prompt = build_system_prompt(
                identity=self._build_identity(),
                memories=memories,
                model=self._model,
            )
        elif memories:
            logger.warning("Memories retrieved but no model set; skipping context injection")
            system_prompt = self._build_identity()
        else:
            system_prompt = self._build_identity()

        error: Exception | None = None
        try:
            result = await self._runner.run(
                system_prompt=system_prompt,
                user_content=message.content,
            )
            content = result.content
        except Exception as exc:
            error = exc
            content = f"Task failed: {exc}"

        # Check for worktree changes regardless of success/failure
        wt_review = ""
        if self._worktree_proxy is not None:
            wt_result = self._worktree_proxy.take_result()
            if wt_result is not None:
                files_str = "\n".join(f"- {f}" for f in wt_result.changed_files)
                wt_review = (
                    f"\n\nChanges ready for review:\n{files_str}\n\n"
                    f"Run: signal worktree merge {wt_result.id}\n"
                    f"Or:  signal worktree discard {wt_result.id}"
                )

        # Error with no worktree state: propagate as before
        if error is not None and not wt_review:
            raise error

        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=content + wt_review,
            parent_id=message.id,
        )
```

- [ ] **Step 4: Run all micro agent tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/agents/test_micro.py -v`
Expected: PASS (all existing tests + 5 new worktree tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/agents/micro.py tests/unit/agents/test_micro.py
git commit -m "feat: integrate WorktreeProxyProtocol into MicroAgent"
```

---

### Task 8: Bootstrap Wiring

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Write tests for worktree bootstrap wiring**

Append to `tests/unit/runtime/test_bootstrap.py`.

First, add the import at the top of the file alongside the existing imports:

```python
from signalagent.worktrees.proxy import WorktreeProxy
```

Then add a new fixture and test class:

```python
@pytest.fixture
def profile_with_worktree_agent():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="coder", skill="coding",
                talks_to=["prime"], plugins=["file_system"],
            ),
        ],
    )


class TestWorktreeBootstrap:
    @pytest.mark.asyncio
    async def test_micro_agent_gets_worktree_proxy(self, tmp_path, config, profile_with_worktree_agent, monkeypatch):
        """Micro-agents should receive a WorktreeProxy instance."""
        mock_ai = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_worktree_agent)

        # host.get() returns BaseAgent; _worktree_proxy is on MicroAgent. type: ignore as above.
        coder = host.get("coder")
        assert coder._worktree_proxy is not None  # type: ignore[union-attr]
        assert isinstance(coder._worktree_proxy, WorktreeProxy)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_write_through_runner_creates_worktree(self, tmp_path, config, profile_with_worktree_agent, monkeypatch):
        """Functional test: a file_system write through the full pipeline creates a worktree."""
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "write", "path": "test.py", "content": "hello"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("coder"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_worktree_agent)
        result = await executor.run("write a test file")

        # The write should have gone to a worktree, not the real workspace
        assert not (tmp_path / "test.py").exists()
        # The response should include worktree review instructions
        assert "signal worktree merge" in result.content
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/runtime/test_bootstrap.py::TestWorktreeBootstrap -v`
Expected: FAIL (MicroAgent not receiving worktree_proxy)

- [ ] **Step 3: Update bootstrap to wire WorktreeProxy**

In `src/signalagent/runtime/bootstrap.py`, add imports at the top (after existing imports):

```python
from signalagent.worktrees.manager import WorktreeManager
from signalagent.worktrees.manifest import WorktreeManifest
from signalagent.worktrees.proxy import WorktreeProxy
```

After the hook registry setup (after line 67), add shared worktree components:

```python
    # Worktree manager and manifest (shared across agents)
    worktree_manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=instance_dir,
    )
    worktree_manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
```

Then update the micro-agent creation loop. For agents **with** spawn capability, after the existing `agent_executor = HookExecutor(...)` line and before creating the runner, insert the proxy:

```python
            # Wrap with worktree proxy (outermost layer)
            worktree_proxy = WorktreeProxy(
                inner=agent_executor,
                hook_registry=hook_registry,
                worktree_manager=worktree_manager,
                manifest=worktree_manifest,
                workspace_root=instance_dir,
                instance_dir=instance_dir,
                agent_name=micro_config.name,
            )

            runner = AgenticRunner(
                ai=ai, tool_executor=worktree_proxy,
                tool_schemas=full_schemas, max_iterations=agent_max,
            )
```

For agents **without** spawn capability, after `tool_executor` is set and before creating the runner:

```python
            # Wrap with worktree proxy (outermost layer)
            worktree_proxy = WorktreeProxy(
                inner=tool_executor,
                hook_registry=hook_registry,
                worktree_manager=worktree_manager,
                manifest=worktree_manifest,
                workspace_root=instance_dir,
                instance_dir=instance_dir,
                agent_name=micro_config.name,
            )

            runner = AgenticRunner(
                ai=ai, tool_executor=worktree_proxy,
                tool_schemas=tool_schemas, max_iterations=agent_max,
            )
```

Finally, update the `MicroAgent` construction to pass the proxy:

```python
        agent = MicroAgent(
            config=micro_config, runner=runner,
            memory_reader=engine, model=model_name,
            worktree_proxy=worktree_proxy,
        )
```

- [ ] **Step 4: Run all bootstrap tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/runtime/test_bootstrap.py -v`
Expected: PASS (all existing + 2 new tests)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS (all tests pass)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat: wire WorktreeProxy into bootstrap for all micro-agents"
```

---

### Task 9: CLI Commands

**Files:**
- Create: `src/signalagent/cli/worktree_cmd.py`
- Modify: `src/signalagent/cli/app.py`
- Create: `tests/unit/cli/test_worktree_cmd.py`

- [ ] **Step 1: Write tests for CLI commands**

```python
# tests/unit/cli/test_worktree_cmd.py
"""Tests for signal worktree CLI commands."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.worktrees.models import WorktreeRecord


runner = CliRunner()


def _make_record(
    id: str = "wt_abc12345",
    status: str = "pending",
    agent_name: str = "coder",
    worktree_path: Path = Path("/tmp/wt"),
) -> WorktreeRecord:
    return WorktreeRecord(
        id=id,
        worktree_path=worktree_path,
        workspace_root=Path("/project"),
        agent_name=agent_name,
        created=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        status=status,
        is_git=True,
        branch_name=f"signal/worktree/{agent_name}_{id}",
    )


class TestWorktreeList:
    @patch("signalagent.cli.worktree_cmd.find_instance")
    @patch("signalagent.cli.worktree_cmd.WorktreeManifest")
    def test_shows_pending_worktrees(
        self, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.list_pending.return_value = [
            _make_record(id="wt_001", agent_name="coder"),
            _make_record(id="wt_002", agent_name="reviewer"),
        ]
        MockManifest.return_value = manifest

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "wt_001" in result.output
        assert "wt_002" in result.output
        assert "coder" in result.output

    @patch("signalagent.cli.worktree_cmd.find_instance")
    @patch("signalagent.cli.worktree_cmd.WorktreeManifest")
    def test_shows_empty_message(
        self, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.list_pending.return_value = []
        MockManifest.return_value = manifest

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "no pending" in result.output.lower() or "No pending" in result.output


class TestWorktreeMerge:
    @patch("signalagent.cli.worktree_cmd.find_instance")
    @patch("signalagent.cli.worktree_cmd.WorktreeManifest")
    @patch("signalagent.cli.worktree_cmd.WorktreeManager")
    def test_merges_and_cleans(
        self,
        MockManager: MagicMock,
        MockManifest: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        record = _make_record(worktree_path=tmp_path / "wt")
        manifest = MagicMock()
        manifest.get.return_value = record
        MockManifest.return_value = manifest
        manager = MagicMock()
        MockManager.return_value = manager

        result = runner.invoke(app, ["worktree", "merge", "wt_abc12345"])
        assert result.exit_code == 0
        manager.merge.assert_called_once()
        manager.cleanup.assert_called_once()
        manifest.append.assert_called_once()
        # Verify status update
        updated = manifest.append.call_args[0][0]
        assert updated.status == "merged"

    @patch("signalagent.cli.worktree_cmd.find_instance")
    @patch("signalagent.cli.worktree_cmd.WorktreeManifest")
    def test_merge_unknown_id(
        self, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.get.return_value = None
        MockManifest.return_value = manifest

        result = runner.invoke(app, ["worktree", "merge", "wt_nonexistent"])
        assert result.exit_code == 1


class TestWorktreeDiscard:
    @patch("signalagent.cli.worktree_cmd.find_instance")
    @patch("signalagent.cli.worktree_cmd.WorktreeManifest")
    @patch("signalagent.cli.worktree_cmd.WorktreeManager")
    def test_discards_and_cleans(
        self,
        MockManager: MagicMock,
        MockManifest: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        record = _make_record(worktree_path=tmp_path / "wt")
        manifest = MagicMock()
        manifest.get.return_value = record
        MockManifest.return_value = manifest
        manager = MagicMock()
        MockManager.return_value = manager

        result = runner.invoke(app, ["worktree", "discard", "wt_abc12345"])
        assert result.exit_code == 0
        manager.merge.assert_not_called()
        manager.cleanup.assert_called_once()
        updated = manifest.append.call_args[0][0]
        assert updated.status == "discarded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/unit/cli/test_worktree_cmd.py -v`
Expected: FAIL (module not found or commands not registered)

- [ ] **Step 3: Implement worktree CLI commands**

```python
# src/signalagent/cli/worktree_cmd.py
"""signal worktree -- manage agent worktrees."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signalagent.core.errors import InstanceError

worktree_app = typer.Typer(
    name="worktree",
    help="Manage agent worktrees.",
    no_args_is_help=True,
)

console = Console()


def _get_instance_dir() -> Path:
    from signalagent.core.config import find_instance
    try:
        return find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)


@worktree_app.command("list")
def list_worktrees() -> None:
    """List pending worktrees awaiting review."""
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    pending = manifest.list_pending()

    if not pending:
        console.print("[dim]No pending worktrees.[/dim]")
        return

    table = Table(title="Pending Worktrees")
    table.add_column("ID", style="bold")
    table.add_column("Agent")
    table.add_column("Created")
    table.add_column("Files", justify="right")
    table.add_column("Git", justify="center")

    from signalagent.worktrees.manager import WorktreeManager

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=instance_dir,
    )

    for r in pending:
        file_count = "?"
        if r.worktree_path.exists():
            try:
                files = manager.changed_files(r.worktree_path)
                file_count = str(len(files))
            except Exception:
                pass

        table.add_row(
            r.id,
            r.agent_name,
            r.created.strftime("%Y-%m-%d %H:%M"),
            file_count,
            "Y" if r.is_git else "N",
        )

    console.print(table)


@worktree_app.command("merge")
def merge_worktree(
    worktree_id: str = typer.Argument(..., help="Worktree ID to merge"),
) -> None:
    """Merge worktree changes into the workspace."""
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest
    from signalagent.worktrees.manager import WorktreeManager

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    record = manifest.get(worktree_id)

    if record is None or record.status != "pending":
        console.print(f"[red]Worktree not found or not pending: {worktree_id}[/red]")
        raise typer.Exit(1)

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=record.workspace_root,
    )

    manager.merge(record.worktree_path)
    manager.cleanup(record.worktree_path, branch_name=record.branch_name)

    updated = record.model_copy(update={"status": "merged"})
    manifest.append(updated)

    console.print(f"[green]Merged worktree {worktree_id} into workspace.[/green]")


@worktree_app.command("discard")
def discard_worktree(
    worktree_id: str = typer.Argument(..., help="Worktree ID to discard"),
) -> None:
    """Discard worktree changes without merging."""
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest
    from signalagent.worktrees.manager import WorktreeManager

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    record = manifest.get(worktree_id)

    if record is None or record.status != "pending":
        console.print(f"[red]Worktree not found or not pending: {worktree_id}[/red]")
        raise typer.Exit(1)

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=record.workspace_root,
    )

    manager.cleanup(record.worktree_path, branch_name=record.branch_name)

    updated = record.model_copy(update={"status": "discarded"})
    manifest.append(updated)

    console.print(f"[yellow]Discarded worktree {worktree_id}.[/yellow]")
```

- [ ] **Step 4: Register worktree commands in app.py**

In `src/signalagent/cli/app.py`, update the `_register_commands` function to add the worktree import and registration:

```python
def _register_commands() -> None:
    import signalagent.cli.init_cmd  # noqa: F401
    import signalagent.cli.talk_cmd  # noqa: F401
    import signalagent.cli.chat_cmd  # noqa: F401
    from signalagent.cli.memory_cmd import memory_app
    from signalagent.cli.sessions_cmd import sessions_app
    from signalagent.cli.worktree_cmd import worktree_app

    app.add_typer(memory_app, name="memory")
    app.add_typer(sessions_app, name="sessions")
    app.add_typer(worktree_app, name="worktree")
```

- [ ] **Step 5: Run CLI tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/unit/cli/test_worktree_cmd.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/cli/worktree_cmd.py src/signalagent/cli/app.py tests/unit/cli/test_worktree_cmd.py
git commit -m "feat: add signal worktree list/merge/discard CLI commands"
```

---

### Task 10: Version Bump, Changelog, Roadmap

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`
- Modify: `docs/dev/roadmap.md`

- [ ] **Step 1: Update VERSION**

Change `VERSION` from `0.9.0` to `0.10.0`.

- [ ] **Step 2: Update CHANGELOG.md**

Add new section at the top (after the header, before `[0.9.0]`):

```markdown
## [0.10.0] - 2026-04-02

### Added
- WorktreeManager: git worktree creation (git worktree add) and directory copy fallback
- WorktreeProxy: per-agent tool executor wrapper with lazy worktree creation on first write
- WorktreeManifest: JSONL persistence for worktree lifecycle tracking
- WorktreeResult and WorktreeRecord Pydantic models
- WorktreeProxyProtocol in core/protocols for dependency injection
- `signal worktree list` command showing pending worktrees
- `signal worktree merge <id>` command copying changed files to workspace
- `signal worktree discard <id>` command removing worktree without merging
- Shared IGNORE_DIRS constant in core/constants (used by FileChangeDetector and WorktreeManager)

### Changed
- MicroAgent accepts optional WorktreeProxyProtocol, appends review instructions after file writes
- MicroAgent preserves worktree state on runner failure (partial changes reviewable)
- Bootstrap wraps each micro-agent's tool executor with WorktreeProxy (outermost layer)
- FileChangeDetector imports IGNORE_DIRS from shared constant instead of local definition
```

- [ ] **Step 3: Update roadmap**

In `docs/dev/roadmap.md`, replace the Phase 8 row in the table:

```markdown
| 8a | Worktrees | Complete | Isolated workspaces, git worktrees, CLI review |
| 8b | Forks | Planned | Parallel approaches, multi-worktree coordination |
```

Update the dependency graph to show 8a/8b split:

```
1 --> 2 --> 3 --> 4 \
               --> 5 --> 6 --> 7
                             --> 8a --> 8b
               --> 9 (also needs 2)
               --> 10 (needs all)
```

- [ ] **Step 4: Run full test suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS (all tests pass, no regressions)

- [ ] **Step 5: Commit**

```bash
git add VERSION CHANGELOG.md docs/dev/roadmap.md
git commit -m "chore: bump version to 0.10.0, update changelog and roadmap for Phase 8a"
```
