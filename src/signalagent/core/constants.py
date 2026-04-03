"""Shared constants used across multiple modules.

Centralised here so no module relies on magic values. Importable from
``signalagent.core.constants``.
"""

IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", ".signal", ".venv", "venv",
})
