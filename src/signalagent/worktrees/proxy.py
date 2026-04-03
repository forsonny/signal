"""WorktreeProxy -- per-agent tool executor wrapper for worktree isolation."""
from __future__ import annotations

import asyncio
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

        # Task-scoping lock for fork serialization (Phase 8b).
        # Fork branches may route to the same agent concurrently.
        # The proxy's per-task state machine (PASSTHROUGH -> ISOLATED ->
        # take_result) must not interleave. MicroAgent acquires this lock
        # around _handle() to serialize concurrent task execution per-proxy.
        # For non-fork usage (signal talk / signal chat), the lock is
        # acquired immediately with no contention -- zero overhead.
        self._lock = asyncio.Lock()

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
        """Execute file_system call against worktree, calling hooks directly.

        Hook lifecycle mirrors HookExecutor.__call__: before hooks run first,
        if any blocks we skip the tool, after hooks always fire.
        Passes agent name and respects fail_closed.
        """
        hooks = self._hook_registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(
                    tool_name, arguments, agent=self._agent_name,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    return ToolResult(
                        output="", error=f"Policy hook error: {e}",
                    )
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
            result = await self._execute_in_worktree(tool_name, arguments)

        assert result is not None

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(
                    tool_name, arguments, result, blocked,
                    agent=self._agent_name,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    logger.error(
                        "Fail-closed hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )
                else:
                    logger.warning(
                        "Hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )

        return result

    async def _execute_in_worktree(self, tool_name: str, arguments: dict) -> ToolResult:
        """Run the file_system call against the worktree-rooted tool."""
        assert self._worktree_tool is not None
        try:
            return await self._worktree_tool.execute(**arguments)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    def task_lock(self) -> asyncio.Lock:
        """Return the task-scoping lock for concurrent branch serialization."""
        return self._lock

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
