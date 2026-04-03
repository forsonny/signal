"""FileChangeDetector -- git status / mtime polling for file changes.

Infrastructure code. Calls subprocess.run() directly -- not through
the tool/hook pipeline. This is scheduler-level infrastructure.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from signalagent.core.constants import IGNORE_DIRS

logger = logging.getLogger(__name__)


class FileChangeDetector:
    """Detects file changes via git status or mtime scanning.

    API: check() -> list[str]
    Returns the current dirty file set if it changed since last check.
    Returns empty list if nothing changed.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialise the detector for a directory.

        Args:
            path: Root directory to monitor. Git detection is deferred
                to the first ``check()`` call.
        """
        self._path = Path(path)
        self._is_git: bool | None = None
        self._last_seen: set[str] = set()
        self._mtime_baseline: dict[str, float] = {}

    def check(self) -> list[str]:
        """Return changed files since last check, or empty list.

        Returns:
            Sorted list of changed file paths, or an empty list if
            nothing changed since the previous call.
        """
        if self._is_git is None:
            self._is_git = (self._path / ".git").is_dir()

        if self._is_git:
            return self._check_git()
        return self._check_mtime()

    def _check_git(self) -> list[str]:
        """Git-mode: parse git status --porcelain output."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self._path,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "git status failed (rc=%d): %s", result.returncode, result.stderr,
                )
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("git status error: %s", e)
            return []

        # Parse porcelain output: each line is "XY filename"
        current: set[str] = set()
        for line in result.stdout.splitlines():
            if len(line) > 3:
                current.add(line[3:].strip())

        if current != self._last_seen:
            self._last_seen = current
            if current:
                return sorted(current)
        return []

    def _check_mtime(self) -> list[str]:
        """Non-git fallback: mtime-based scanning."""
        current: dict[str, float] = {}
        try:
            for child in self._path.rglob("*"):
                if child.is_file():
                    # Skip ignored directories
                    parts = child.relative_to(self._path).parts
                    if any(p in IGNORE_DIRS for p in parts):
                        continue
                    rel = str(child.relative_to(self._path))
                    current[rel] = child.stat().st_mtime
        except OSError as e:
            logger.warning("mtime scan error: %s", e)
            return []

        current_keys = set(current.keys())
        baseline_keys = set(self._mtime_baseline.keys())

        changed: set[str] = set()
        # New or modified files
        for path, mtime in current.items():
            if path not in self._mtime_baseline or self._mtime_baseline[path] != mtime:
                changed.add(path)
        # Deleted files
        changed.update(baseline_keys - current_keys)

        self._mtime_baseline = current

        if changed:
            return sorted(changed)
        return []
