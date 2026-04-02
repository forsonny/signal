"""Tests for shared constants."""
from signalagent.core.constants import IGNORE_DIRS


class TestIgnoreDirs:
    def test_contains_expected_dirs(self) -> None:
        expected = {".git", "__pycache__", "node_modules", ".signal", ".venv", "venv"}
        assert expected == IGNORE_DIRS

    def test_is_frozenset(self) -> None:
        assert isinstance(IGNORE_DIRS, frozenset)
