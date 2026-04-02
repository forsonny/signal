# Phase 8b: Forks -- Parallel Execution Paths

## Overview

Phase 8b adds a `signal fork` CLI command that runs N user-defined tasks concurrently, each in its own worktree. The user reviews results with the existing 8a CLI commands (`signal worktree list/merge/discard`) and merges the winner.

This builds on the worktree isolation from Phase 8a. Fork branches are normal tasks that route through the existing Executor -> Prime -> micro-agent pipeline. The fork infrastructure's only job is to run them in parallel and present results together.

## Architecture

### Components

| Component | Module | Responsibility |
|-----------|--------|----------------|
| ForkRunner | `worktrees/fork.py` | Async orchestrator. Runs N tasks concurrently via asyncio.gather with semaphore bounding. Collects results by diffing manifest before/after. |
| ForkResult | `worktrees/models.py` | Data model for one fork branch result: task, response, worktree ID, changed files, success/failure. |
| ForkConfig | `core/models.py` | Profile config for max concurrent branches (default 2). |
| `signal fork` | `cli/fork_cmd.py` | CLI entry point. Takes N task descriptions as arguments, runs ForkRunner, prints summary. |

### What Changes

- New `ForkRunner` in `worktrees/fork.py`.
- New `ForkResult` model in `worktrees/models.py`.
- New `ForkConfig` model in `core/models.py`, added to Profile.
- WorktreeProxy gains `asyncio.Lock` and `task_lock()` method for concurrent branch serialization.
- WorktreeProxyProtocol gains `task_lock()` method.
- MicroAgent acquires `task_lock()` around `_handle()` body.
- New `signal fork` CLI command in `cli/fork_cmd.py`.
- blank.yaml updated with fork section.

### What Does Not Change

- WorktreeManager -- already handles multiple worktrees.
- WorktreeManifest -- already tracks multiple pending worktrees.
- Executor -- stateless per-call, safe for concurrent `run()` calls.
- MessageBus -- dispatches independently per message.
- PrimeAgent -- routes fork branches like any other task.
- `signal worktree list/merge/discard` -- unchanged, used to review fork results.

## ForkRunner

The orchestrator. Created by the `signal fork` CLI command.

### Execution Flow

1. Read the manifest's pending worktree IDs (snapshot before).
2. Create an `asyncio.Semaphore(max_concurrent)` for concurrency bounding.
3. For each task description, create a coroutine that:
   - Acquires the semaphore.
   - Calls `executor.run(task_description)`.
   - Releases the semaphore.
   - Returns the `ExecutorResult`.
4. Run all coroutines with `asyncio.gather(return_exceptions=True)`.
5. For each ExecutorResult, extract the worktree ID from the response content (the `signal worktree merge <id>` line that MicroAgent appends). If no worktree line is present, the branch produced no file changes.
6. Build a `ForkResult` per branch with the extracted worktree ID, changed files (from manifest lookup), and response.
7. Return a list of `ForkResult` -- one per branch.

### Concurrency Model

- `asyncio.Semaphore(max_concurrent)` bounds parallel execution (default 2).
- One Executor instance, N concurrent `run()` calls.
- Branches to the same agent serialize via the proxy's `task_lock()` (LLM calls happen inside the lock, so same-agent branches are effectively sequential).
- Branches to different agents run fully parallel.
- The semaphore bounds overall concurrency regardless of agent routing.

### Worktree ID Extraction

Each fork branch's response content includes `signal worktree merge <id>` if the agent wrote files (appended by MicroAgent in Phase 8a). The ForkRunner extracts the worktree ID from this line using a simple regex (`r"signal worktree merge (wt_[a-f0-9]+)"`). If no match, the branch produced no file changes.

Changed files for each worktree are retrieved from the manifest via `manifest.get(worktree_id)` and `manager.changed_files(worktree_path)`. This reuses the existing manifest lookup -- no snapshot diffing needed.

## ForkResult Model

Added to `worktrees/models.py`. Pydantic model with `extra="forbid"`.

```
ForkResult:
    branch_index: int          # 0-based, matches CLI argument order
    task_description: str      # the user's original prompt for this branch
    response: str              # agent's response text
    worktree_id: str | None    # worktree ID if files were changed, None if read-only
    changed_files: list[str]   # files modified (empty if no writes)
    success: bool              # True if executor.run() didn't error
    error: str | None = None   # error message if failed
```

## WorktreeProxy Lock

The existing WorktreeProxy gains an `asyncio.Lock` to serialize concurrent access from fork branches routed to the same agent.

### Changes

- `self._lock = asyncio.Lock()` in `__init__`.
- `def task_lock(self) -> asyncio.Lock:` returns the lock instance.
- Comment explaining why a "per-agent, sequential" proxy needs a lock: fork branches may route to the same agent concurrently, and the proxy's per-task state machine (PASSTHROUGH -> ISOLATED -> take_result) must not interleave.

### Lock Scope

The lock is acquired in MicroAgent._handle() and released after take_result(). The full task lifecycle (LLM calls + tool calls + take_result) executes inside the lock. This means:

- Branches to the same agent: serialized (LLM calls inside lock).
- Branches to different agents: fully parallel (separate proxy instances, separate locks).
- Non-fork usage (signal talk / signal chat): lock acquired immediately with no contention (no-op overhead).

### Why Not Per-Tool-Call Locking

Locking per `__call__` would allow interleaved tool calls from different branches on the same proxy, corrupting the PASSTHROUGH/ISOLATED state machine. The lock must cover the entire task lifecycle to ensure one branch completes its worktree cycle before the next starts.

## WorktreeProxyProtocol

Gains one method:

```python
class WorktreeProxyProtocol(Protocol):
    def take_result(self) -> Any: ...
    def task_lock(self) -> Any: ...  # returns asyncio.Lock
```

Return type is `Any` to avoid importing asyncio in the protocol (same pattern as `take_result` returning `Any` to avoid importing WorktreeResult into core).

## MicroAgent Integration

MicroAgent._handle() acquires the task lock when proxy is not None:

```python
async def _handle(self, message):
    if self._worktree_proxy is not None:
        async with self._worktree_proxy.task_lock():
            return await self._handle_inner(message)
    return await self._handle_inner(message)
```

The existing _handle() body moves to `_handle_inner()`. Agents without a proxy (sub-agents from Phase 4c) are unaffected.

## ForkConfig

Added to `core/models.py` and Profile. Pydantic model with `extra="forbid"`.

```
ForkConfig:
    max_concurrent_branches: int = 2   # default matches typical personal API rate limits
```

Profile gains `fork: ForkConfig = Field(default_factory=ForkConfig)` alongside existing heartbeat, hooks, plugins configs.

blank.yaml updated:

```yaml
fork:
  max_concurrent_branches: 2
```

## CLI: signal fork

### Usage

```
signal fork "task A" "task B" [--concurrency N]
```

- Positional arguments: N task descriptions (minimum 2).
- `--concurrency N`: override profile's `max_concurrent_branches` for this invocation.

### Execution

1. Bootstrap the runtime (same as `signal talk`).
2. Read `profile.fork.max_concurrent_branches` (or `--concurrency` override).
3. Create `ForkRunner` with the executor and concurrency cap.
4. Run all branches.
5. Print summary and exit.

### Output Format

```
Fork complete: 2 branches

--- Branch 1: "fix using dataclasses" ---
Status: Success
Response: [first 200 chars]
Changed files: 3
Worktree: wt_abc12345

--- Branch 2: "fix using TypedDict" ---
Status: Success
Response: [first 200 chars]
Changed files: 2
Worktree: wt_def67890

Review with: signal worktree list
Merge winner: signal worktree merge <id>
Discard rest: signal worktree discard <id>
```

### Exit Codes

- 0: at least one branch succeeded.
- 1: all branches failed.

## Done-When Criteria

### ForkRunner
1. Takes a list of task descriptions, an Executor, and a concurrency cap.
2. Runs N tasks concurrently via `asyncio.gather()` with `asyncio.Semaphore(max_concurrent)`.
3. Each branch calls `executor.run(task_description)` -- same pipeline as `signal talk`.
4. Extracts worktree IDs from each branch's response content via regex (`signal worktree merge (wt_[a-f0-9]+)`).
5. Returns a list of `ForkResult` -- one per branch, with worktree ID extracted from response.
6. Branches that fail produce `ForkResult` with `success=False` and error message.
7. Branches that produce no file changes produce `ForkResult` with `worktree_id=None`.

### ForkResult
8. Contains branch_index, task_description, response, worktree_id (optional), changed_files, success, error (optional).
9. Pydantic model with `extra="forbid"`.

### WorktreeProxy Lock
10. WorktreeProxy gains `asyncio.Lock` in `__init__`.
11. `task_lock()` method returns the lock instance.
12. Lock is a no-op for non-fork usage (no contention, acquired immediately).
13. Comment in proxy explaining why a "per-agent, sequential" proxy needs a lock.

### WorktreeProxyProtocol
14. Protocol gains `task_lock() -> Any`.

### MicroAgent
15. `_handle()` acquires `task_lock()` when proxy is not None.
16. Full task lifecycle (run -> take_result) executes inside the lock.
17. Agents without proxy (sub-agents) are unaffected.

### ForkConfig
18. `ForkConfig` model with `max_concurrent_branches: int = 2`.
19. Added to Profile alongside existing config models.
20. blank.yaml updated with fork section.

### CLI: signal fork
21. `signal fork "task A" "task B" ...` takes N positional task descriptions.
22. `--concurrency N` flag overrides profile's `max_concurrent_branches`.
23. Runs bootstrap, creates ForkRunner, executes all branches.
24. Prints summary: per-branch status, response preview, changed files, worktree ID.
25. Prints footer with `signal worktree list/merge/discard` instructions.
26. Exit code 0 if at least one branch succeeded, 1 if all failed.

### Integration
27. Fork branches route through Prime independently -- no fork-aware routing.
28. Fork branches that write files create separate pending worktrees in the manifest.
29. `signal worktree list` shows all pending worktrees from the fork.
30. `signal worktree merge <id>` and `signal worktree discard <id>` work unchanged on fork worktrees.
31. Branches to the same agent serialize via the proxy lock. Branches to different agents run fully parallel.

### Version and Docs
32. VERSION bumped to 0.11.0.
33. CHANGELOG updated with Phase 8b section.
34. Roadmap updated: Phase 8b marked Complete.

### Regression
35. `signal talk` and `signal chat` are unaffected by the proxy lock addition -- lock acquired and released immediately with no contention. Verify existing talk/chat tests still pass with the lock in place.
