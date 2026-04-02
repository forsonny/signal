# Phase 8a: Worktrees -- Isolated Agent Workspaces

## Overview

Phase 8a adds a worktree isolation layer to the agent execution pipeline. When a micro-agent writes files via FileSystemTool, those writes go to an isolated git worktree (or directory copy for non-git workspaces) instead of the real workspace. The user reviews the diff and explicitly merges or discards via CLI commands. No changes touch the real workspace without approval.

This is the safety foundation for Phase 8b (Forks), which adds parallel execution paths using multiple worktrees.

## Architecture

### Components

| Component | Module | Responsibility |
|-----------|--------|----------------|
| WorktreeManager | `worktrees/manager.py` | Creates/destroys git worktrees and directory copies. Pure filesystem mechanics. No awareness of agents or the message bus. |
| WorktreeProxy | `worktrees/proxy.py` | Per-agent callable in the tool execution chain. Intercepts `file_system` calls, routes reads/writes through worktree when active. Creates worktree lazily on first write via WorktreeManager. |
| WorktreeResult | `worktrees/models.py` | Data model returned by proxy when writes occurred. Contains worktree ID, changed files, diff, review instructions. |
| WorktreeRecord | `worktrees/models.py` | Manifest entry tracking worktree lifecycle (pending/merged/discarded). |
| WorktreeProxyProtocol | `core/protocols.py` | Protocol for MicroAgent dependency. Exposes `take_result()` only. |

### Execution Chain

```
Runner calls tool_executor
  -> WorktreeProxy (intercepts file_system, passes everything else through)
    -> HookExecutor (before/after hooks on all tool calls)
      -> inner_executor (registry lookup + execution)
        -> FileSystemTool (real workspace)
```

WorktreeProxy is the outermost executor layer. It wraps the HookExecutor chain. Non-`file_system` calls pass through the full chain unchanged in all modes.

### What Changes

- Bootstrap wraps each micro-agent's tool executor with a WorktreeProxy.
- MicroAgent gains an optional `WorktreeProxyProtocol` dependency for reading worktree results after task completion.
- Three new CLI commands: `signal worktree list`, `signal worktree merge <id>`, `signal worktree discard <id>`.
- `IGNORE_DIRS` promoted to a shared constant.

### What Does Not Change

- AgenticRunner -- no changes.
- MessageBus -- no changes.
- ToolRegistry -- no changes.
- PrimeAgent -- no changes. Zero worktree awareness.
- FileSystemTool -- no changes. The proxy sits upstream.
- HookExecutor -- no changes to the class itself.

## WorktreeManager

Pure filesystem mechanics. Creates and destroys worktrees. Stateless -- it executes operations, does not track worktree lifecycle (that is the manifest's job).

### Git Detection

Checks `(workspace / ".git").is_dir()` once at construction. Same pattern as FileChangeDetector in the heartbeat module.

### Git Mode (workspace is a git repo)

- **create(workspace, name)** -- `git worktree add -b signal/worktree/{name} {target_path} HEAD`. Target path is `instance_dir/data/worktrees/{name}/`. Creates a linked checkout at HEAD.
- **diff(worktree_path)** -- `git diff HEAD` inside the worktree. Returns unified diff string.
- **changed_files(worktree_path)** -- `git diff --name-only HEAD` inside the worktree. Returns list of relative file paths.
- **merge(worktree_path, workspace)** -- Copies changed files from worktree to workspace. File copy, not git merge. Git merge with conflict resolution is a Phase 8b concern.
- **discard(worktree_path)** -- Deletes the worktree directory. Runs `git worktree prune`. Deletes the branch (`git branch -D signal/worktree/{name}`).

### Non-Git Fallback (directory copy mode)

- **create** -- `shutil.copytree(workspace, target_path, ignore=...)` with `IGNORE_DIRS` filter. Clearly second-class: no branching, no native diff, basic file operations.
- **diff** -- File-by-file comparison between worktree and original workspace. Produces basic unified diff.
- **changed_files** -- Compares file hashes (or mtimes) between worktree and original.
- **merge** -- Copies changed files from worktree to workspace.
- **discard** -- Deletes the worktree directory.

### Implementation Details

- All git commands use `subprocess.run()` directly -- infrastructure, not the tool pipeline.
- `IGNORE_DIRS` is a shared constant (promoted from `heartbeat/detector.py`) used by both FileChangeDetector and WorktreeManager's `copytree` filter. Contains: `.git`, `__pycache__`, `node_modules`, `.signal`, `.venv`, `venv`.

## WorktreeProxy

Per-agent callable that the AgenticRunner holds as its `tool_executor`. Manages per-task worktree state. Created at bootstrap, persists for the agent's lifetime, resets state between tasks.

### State Machine

```
PASSTHROUGH -> ISOLATED
     (on first file_system write)
```

Two states, one transition, no going back within a task.

### PASSTHROUGH Mode

No worktree exists. All `file_system` calls pass through to the inner chain (HookExecutor -> inner_executor -> FileSystemTool at real workspace). Hooks fire naturally through the chain. Reads hit the real workspace.

### ISOLATED Mode

Worktree exists. The proxy intercepts `file_system` calls and executes them against a worktree-rooted FileSystemTool instance.

- **Writes**: go to worktree-rooted FileSystemTool.
- **Reads**: go to worktree-rooted FileSystemTool (agent sees its own changes).
- **Hook preservation**: The proxy calls `hook_registry.before_tool_call(name, args)` and `hook_registry.after_tool_call(name, args, result, blocked=False)` directly with the agent's original (logical) path arguments. The `blocked=False` matches the full Phase 4b hook signature (the proxy is executing the tool, not blocking it). Hooks never see worktree-internal paths.
- **Non-file_system calls**: always pass through the full inner chain regardless of mode.

### Lazy Creation

The proxy inspects the `action` argument of `file_system` calls. On the first `write`, it calls `WorktreeManager.create()`, constructs a new FileSystemTool rooted at the worktree path, and transitions to ISOLATED. Reads before any write go through the inner chain to the real workspace (zero overhead for read-only tasks).

### Injected Dependencies

- `inner` -- the HookExecutor-wrapped chain, for pass-through calls.
- `hook_registry` -- HookRegistry instance, for direct hook calls in ISOLATED mode.
- `worktree_manager` -- WorktreeManager instance, for creating worktrees.
- `workspace_root` -- Path, the real workspace.
- `instance_dir` -- Path, for worktree target path generation.
- `agent_name` -- str, for worktree naming.

### take_result()

```python
def take_result(self) -> WorktreeResult | None:
```

Returns `WorktreeResult` if writes occurred during the task, `None` otherwise. Resets internal state to PASSTHROUGH for the next task. Does not clean up the worktree directory -- that is the user's job via CLI merge/discard.

### Signature

```python
async def __call__(self, tool_name: str, arguments: dict) -> ToolResult
```

Same callable signature as every other executor in the chain.

## WorktreeResult and WorktreeRecord

### WorktreeResult

Returned by `WorktreeProxy.take_result()` when writes occurred during a task. Pydantic model with `extra="forbid"`.

```
WorktreeResult:
    id: str                  # wt_ + 8 hex chars
    worktree_path: Path
    workspace_root: Path
    changed_files: list[str] # relative paths
    diff: str                # unified diff
    agent_name: str
    is_git: bool
```

### WorktreeRecord

Manifest entry persisted to JSONL. Pydantic model with `extra="forbid"`.

```
WorktreeRecord:
    id: str
    worktree_path: Path
    workspace_root: Path
    agent_name: str
    created: datetime
    status: str              # "pending" | "merged" | "discarded"
    is_git: bool
    branch_name: str | None  # git branch name, if git mode
```

### Manifest

`instance_dir/data/worktrees/manifest.jsonl` -- one JSON object per line, append-only. Same pattern as SessionManager and LogToolCallsHook.

- Proxy writes a record with status "pending" on worktree creation.
- `signal worktree merge` updates status to "merged", cleans up directory.
- `signal worktree discard` updates status to "discarded", cleans up directory.
- Status updates are appended as new lines. Reader builds a `dict[id, WorktreeRecord]` by iterating all lines -- later entries overwrite earlier ones for the same ID. `signal worktree list` filters the resolved dict for `status == "pending"`.
- Reader skips malformed lines with a logged warning (crash tolerance).

## MicroAgent Integration

### WorktreeProxyProtocol

Added to `core/protocols.py`:

```python
class WorktreeProxyProtocol(Protocol):
    def take_result(self) -> Any: ...
```

MicroAgent holds `Optional[WorktreeProxyProtocol]`. Sub-agents from Phase 4c pass `None` (no worktree isolation for ephemeral sub-agents).

### Post-Task Flow

1. Task arrives at `MicroAgent._handle()`.
2. MicroAgent calls `runner.run()`. During execution, the proxy may create a worktree.
3. `runner.run()` returns `RunnerResult`.
4. MicroAgent calls `proxy.take_result()` if proxy is not `None`.
5. If `WorktreeResult` exists, MicroAgent appends review instructions to response content: changed file list, diff summary, and CLI commands (`signal worktree merge <id>` / `signal worktree discard <id>`).
6. If `WorktreeResult` is `None` (read-only task), response flows through normally with zero overhead.

### Failure Case

If `runner.run()` throws or hits the iteration limit, MicroAgent still calls `take_result()`. Partial writes in the worktree are preserved. The response includes failure context alongside the review instructions. Same review flow as success -- every worktree, success or failure, goes through the same "show diff, CLI merge/discard" path.

## Review Flow

CLI-only review for Phase 8a. No conversational review, no Prime state management.

### Agent Output

When an agent produces file changes, its response includes:

```
I modified the following files:
- src/main.py
- src/utils.py

Changes ready for review. Run:
  signal worktree merge wt_abc12345
to apply changes to your workspace, or:
  signal worktree discard wt_abc12345
to discard them.
```

### CLI Commands

- `signal worktree list` -- shows pending worktrees with ID, agent name, timestamp, file count, status. Reads from manifest.
- `signal worktree merge <id>` -- copies changed files from worktree to real workspace, updates manifest status to "merged", cleans up worktree directory (and git branch in git mode).
- `signal worktree discard <id>` -- updates manifest status to "discarded", cleans up worktree directory (and git branch in git mode).

### Mode Behavior

Both `signal talk` (one-shot) and `signal chat` (interactive REPL) produce the same agent output with worktree ID and CLI commands. Neither mode auto-cleans worktrees on exit. Worktrees persist on disk until the user explicitly merges or discards via CLI.

- **talk**: prints review instructions, process exits, user runs CLI commands from terminal.
- **chat**: prints review instructions inline, user can continue working, runs CLI commands from a separate terminal.

## Bootstrap Wiring

### WorktreeManager

Single instance created at bootstrap. Shared across all agents. Receives `instance_dir` and `workspace_root` (the real workspace path).

### WorktreeProxy (per micro-agent)

For each micro-agent, bootstrap creates a `WorktreeProxy` that wraps the existing HookExecutor-chain tool executor. The proxy becomes the `tool_executor` passed to `AgenticRunner`.

### MicroAgent Construction

MicroAgent receives the `WorktreeProxy` instance as `Optional[WorktreeProxyProtocol]` alongside the runner. Sub-agents spawned via `SpawnSubAgentTool` receive `None` -- no worktree isolation for ephemeral sub-agents.

### Wrapping Order

```python
inner_executor        # registry lookup + error handling
hook_executor         # HookExecutor(inner=inner_executor, registry=hook_registry)
worktree_proxy        # WorktreeProxy(inner=hook_executor, hook_registry=..., ...)

runner = AgenticRunner(ai=ai, tool_executor=worktree_proxy, ...)
agent = MicroAgent(config=..., runner=runner, worktree_proxy=worktree_proxy, ...)
```

### Shared Constant

`IGNORE_DIRS` promoted from `heartbeat/detector.py` to a shared location (e.g., `core/constants.py`). Both `FileChangeDetector` and `WorktreeManager` import from the shared location.

## Done-When Criteria

### WorktreeManager
1. `create()` produces a git worktree (`git worktree add`) when workspace is a git repo.
2. `create()` produces a directory copy (`shutil.copytree` with IGNORE_DIRS filter) when workspace is not a git repo.
3. `diff()` returns unified diff for both git and non-git worktrees.
4. `changed_files()` returns list of modified file paths for both modes.
5. `merge()` copies changed files from worktree to workspace (file copy, not git merge).
6. `discard()` deletes worktree directory and runs `git worktree prune` in git mode.
7. Git detection uses `(workspace / ".git").is_dir()` -- same pattern as FileChangeDetector.
8. All git operations use `subprocess.run()` directly -- infrastructure, not tool pipeline.

### WorktreeProxy
9. PASSTHROUGH mode: `file_system` calls pass through to inner chain unchanged.
10. ISOLATED mode: `file_system` writes go to worktree-rooted FileSystemTool.
11. ISOLATED mode: `file_system` reads go to worktree (agent sees its own changes).
12. Transition: first `file_system` write triggers lazy worktree creation via WorktreeManager.
13. Non-`file_system` calls always pass through regardless of mode.
14. Hooks fire in both modes -- ISOLATED mode calls `HookRegistry.before_tool_call` / `after_tool_call(name, args, result, blocked=False)` directly with original (logical) path arguments.
15. `take_result()` returns `WorktreeResult` if writes occurred, `None` otherwise, and resets state to PASSTHROUGH.

### WorktreeResult Model
16. Contains worktree ID, path, changed files, diff, agent name, is_git flag.
17. Pydantic model with `extra="forbid"`.

### Manifest
18. JSONL manifest at `instance_dir/data/worktrees/manifest.jsonl`.
19. Append-only writes, skip-bad-lines tolerance on read (same as SessionManager).
20. Records track id, path, workspace_root, agent_name, created, status, is_git, branch_name.

### WorktreeProxyProtocol
21. Protocol in `core/protocols.py` with `take_result() -> WorktreeResult | None`.
22. MicroAgent holds `Optional[WorktreeProxyProtocol]` -- `None` for sub-agents.

### MicroAgent Integration
23. After `runner.run()`, calls `proxy.take_result()` if proxy is not None.
24. If `WorktreeResult` exists, appends review instructions (file list, diff summary, CLI commands) to response content.
25. Same flow for success and failure -- partial worktrees preserved for review.

### Bootstrap Wiring
26. WorktreeManager created once, shared across agents.
27. WorktreeProxy created per-agent, injected as tool_executor to AgenticRunner.
28. WorktreeProxy wraps HookExecutor chain (outermost executor layer).
29. MicroAgent receives proxy reference via `WorktreeProxyProtocol`.
30. Sub-agents (from Phase 4c) receive `None` for proxy -- no worktree isolation.

### CLI Commands
31. `signal worktree list` -- shows pending worktrees from manifest.
32. `signal worktree merge <id>` -- copies changed files to workspace, updates manifest, cleans up.
33. `signal worktree discard <id>` -- updates manifest, cleans up worktree directory.

### Shared Constant
34. `IGNORE_DIRS` promoted to shared location (used by FileChangeDetector and WorktreeManager).

### Version and Docs
35. VERSION bumped to 0.10.0.
36. CHANGELOG updated with Phase 8a section.
37. Roadmap updated (Phase 8 split into 8a/8b, 8a marked Complete).

### Mode Behavior
38. `signal talk` and `signal chat` both work with worktrees -- talk prints review instructions and exits, chat prints inline. Both produce the same agent output with worktree ID and CLI commands. Neither mode auto-cleans worktrees on exit.
