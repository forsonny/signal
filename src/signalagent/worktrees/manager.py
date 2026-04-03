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
        """Initialise the manager.

        Args:
            instance_dir: Signal instance directory (``~/.signal/``).
            workspace_root: Root of the user's project workspace.
        """
        self._instance_dir = instance_dir
        self._workspace_root = workspace_root
        self._worktrees_dir = instance_dir / "data" / "worktrees"
        self._is_git: bool = (workspace_root / ".git").is_dir()

    @property
    def is_git(self) -> bool:
        """Return ``True`` if the workspace is a git repository."""
        return self._is_git

    def create(self, name: str) -> Path:
        """Create a worktree (git branch or directory copy).

        Args:
            name: Unique name used for the directory and git branch.

        Returns:
            Absolute path to the newly created worktree.
        """
        self._worktrees_dir.mkdir(parents=True, exist_ok=True)
        target = self._worktrees_dir / name
        if self._is_git:
            return self._create_git(name, target)
        return self._create_copy(target)

    def diff(self, worktree_path: Path) -> str:
        """Return unified diff of changes in the worktree.

        Args:
            worktree_path: Absolute path to the worktree directory.

        Returns:
            Unified diff string (may be empty if no changes).
        """
        if self._is_git:
            return self._diff_git(worktree_path)
        return self._diff_copy(worktree_path)

    def changed_files(self, worktree_path: Path) -> list[str]:
        """Return sorted list of changed file paths (relative).

        Args:
            worktree_path: Absolute path to the worktree directory.

        Returns:
            Sorted list of workspace-relative paths that differ.
        """
        if self._is_git:
            return self._changed_files_git(worktree_path)
        return self._changed_files_copy(worktree_path)

    def merge(self, worktree_path: Path) -> None:
        """Copy changed files from worktree back to the workspace.

        Args:
            worktree_path: Absolute path to the worktree directory.
        """
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
        """Remove worktree directory and prune git references.

        Args:
            worktree_path: Absolute path to the worktree to remove.
            branch_name: Git branch to delete, if applicable.
        """
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
        wt_dir = self._worktrees_dir.resolve()

        def _ignore(directory: str, contents: list[str]) -> set[str]:
            ignored = set(shutil.ignore_patterns(*IGNORE_DIRS)(directory, contents))
            # Also skip the worktrees directory itself to prevent recursive copies
            for name in contents:
                if (Path(directory) / name).resolve() == wt_dir:
                    ignored.add(name)
            return ignored

        shutil.copytree(
            self._workspace_root, target,
            ignore=_ignore,
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
        """Walk *root*, returning relative paths while skipping IGNORE_DIRS.

        Args:
            root: Directory to walk.

        Returns:
            Set of workspace-relative file path strings.
        """
        wt_dir = self._worktrees_dir.resolve()
        result: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS
                and (Path(dirpath) / d).resolve() != wt_dir
            ]
            for f in filenames:
                full = Path(dirpath) / f
                result.add(str(full.relative_to(root)))
            dirnames.sort()
        return result

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
