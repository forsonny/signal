"""Shared constants used across multiple modules."""

IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", ".signal", ".venv", "venv",
})
