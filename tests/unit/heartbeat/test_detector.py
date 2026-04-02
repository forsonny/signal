"""Unit tests for FileChangeDetector."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from signalagent.heartbeat.detector import FileChangeDetector


class TestGitDetection:
    def test_detects_git_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)
        detector.check()  # triggers git detection
        assert detector._is_git is True

    def test_detects_non_git(self, tmp_path):
        detector = FileChangeDetector(tmp_path)
        detector.check()
        assert detector._is_git is False


class TestGitModeCheck:
    def test_returns_dirty_files_on_first_change(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: no dirty files (baseline)
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr="",
            )
            result = detector.check()
            assert result == []

            # Second check: two dirty files
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n?? new_file.txt\n", stderr="",
            )
            result = detector.check()
            assert set(result) == {"src/main.py", "new_file.txt"}

    def test_returns_empty_when_dirty_set_unchanged(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: dirty
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n", stderr="",
            )
            result = detector.check()
            assert result == ["src/main.py"]

            # Second check: same dirty set
            result = detector.check()
            assert result == []

    def test_resets_silently_when_dirty_becomes_clean(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: dirty
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n", stderr="",
            )
            detector.check()

            # Second check: clean (files committed)
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr="",
            )
            result = detector.check()
            assert result == []  # silent reset, no trigger

    def test_new_dirty_file_triggers_again(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First: one dirty file
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M a.py\n", stderr="",
            )
            detector.check()

            # Second: different dirty file
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M b.py\n", stderr="",
            )
            result = detector.check()
            assert result == ["b.py"]


class TestMtimeMode:
    def test_detects_new_file(self, tmp_path):
        detector = FileChangeDetector(tmp_path)

        # Baseline: empty
        result = detector.check()
        assert result == []

        # Add a file
        (tmp_path / "hello.txt").write_text("hi")
        result = detector.check()
        assert "hello.txt" in result

    def test_returns_empty_when_unchanged(self, tmp_path):
        (tmp_path / "hello.txt").write_text("hi")
        detector = FileChangeDetector(tmp_path)

        # First check: baseline
        detector.check()

        # Second check: no changes
        result = detector.check()
        assert result == []

    def test_detects_deleted_file(self, tmp_path):
        (tmp_path / "gone.txt").write_text("bye")
        detector = FileChangeDetector(tmp_path)

        # Baseline: file exists
        detector.check()

        # Delete file
        (tmp_path / "gone.txt").unlink()
        result = detector.check()
        assert "gone.txt" in result

    def test_detects_modified_file(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("v1")
        detector = FileChangeDetector(tmp_path)

        # Baseline
        detector.check()

        # Modify (write new content to change mtime)
        import time
        time.sleep(0.05)  # ensure mtime differs
        f.write_text("v2")
        result = detector.check()
        assert "data.txt" in result

    def test_skips_ignored_dirs(self, tmp_path):
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_text("bytecode")

        detector = FileChangeDetector(tmp_path)
        result = detector.check()
        assert result == []


class TestErrorHandling:
    def test_git_nonzero_returncode_returns_empty(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: not a git repo",
            )
            result = detector.check()
            assert result == []

    def test_git_subprocess_failure_returns_empty(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError("git not found")
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = detector.check()
            assert result == []

    def test_git_timeout_returns_empty(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            mock_sub.run.side_effect = subprocess.TimeoutExpired("git", 10)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = detector.check()
            assert result == []
