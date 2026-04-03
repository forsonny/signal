"""ForkRunner -- orchestrates parallel fork branch execution."""
from __future__ import annotations

import asyncio
import logging
import re

from signalagent.runtime.executor import Executor
from signalagent.worktrees.manager import WorktreeManager
from signalagent.worktrees.manifest import WorktreeManifest
from signalagent.worktrees.models import ForkResult, WORKTREE_MERGE_PATTERN

logger = logging.getLogger(__name__)


class ForkRunner:
    """Runs N tasks concurrently with semaphore-bounded parallelism.

    Each branch calls executor.run() -- same pipeline as signal talk.
    Worktree IDs are extracted from the agent response text using
    WORKTREE_MERGE_PATTERN.
    """

    def __init__(
        self,
        executor: Executor,
        manifest: WorktreeManifest,
        manager: WorktreeManager,
        max_concurrent: int = 2,
    ) -> None:
        """Create a fork runner.

        Args:
            executor: The runtime executor used to run each branch.
            manifest: Worktree manifest for looking up branch records.
            manager: Worktree manager for querying changed files.
            max_concurrent: Maximum number of branches that execute
                simultaneously (controlled by an ``asyncio.Semaphore``).
        """
        self._executor = executor
        self._manifest = manifest
        self._manager = manager
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, tasks: list[str]) -> list[ForkResult]:
        """Run all tasks concurrently and return results.

        Args:
            tasks: List of task description strings, one per branch.

        Returns:
            A list of ``ForkResult`` objects, one per branch, in the
            same order as *tasks*.
        """

        async def run_branch(index: int, task: str) -> ForkResult:
            async with self._semaphore:
                try:
                    result = await self._executor.run(task)
                except Exception as exc:
                    return ForkResult(
                        branch_index=index,
                        task_description=task,
                        response="",
                        success=False,
                        error=str(exc),
                    )

            if result.error:
                return ForkResult(
                    branch_index=index,
                    task_description=task,
                    response=result.content,
                    success=False,
                    error=result.error,
                )

            # Extract worktree ID from response
            worktree_id = None
            changed_files: list[str] = []
            if result.content:
                match = re.search(WORKTREE_MERGE_PATTERN, result.content)
                if match:
                    worktree_id = match.group(1)
                    record = self._manifest.get(worktree_id)
                    if record and record.worktree_path.exists():
                        try:
                            changed_files = self._manager.changed_files(
                                record.worktree_path,
                            )
                        except Exception:
                            logger.warning(
                                "Failed to get changed files for %s", worktree_id,
                            )

            return ForkResult(
                branch_index=index,
                task_description=task,
                response=result.content,
                worktree_id=worktree_id,
                changed_files=changed_files,
                success=True,
            )

        coros = [run_branch(i, task) for i, task in enumerate(tasks)]
        results = await asyncio.gather(*coros)
        return list(results)
