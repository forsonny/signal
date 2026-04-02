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
