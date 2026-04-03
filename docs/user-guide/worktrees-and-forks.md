# Worktrees & Forks

**What you'll learn:**

- What worktrees are and how they isolate agent file writes
- How to review, merge, and discard worktree changes with the CLI
- What forks are and how they enable parallel approach exploration
- How to run multiple approaches in parallel and pick the winner
- Configuration options for concurrency

---

## Worktrees

### What worktrees are

A worktree is an isolated workspace created automatically when an agent writes files. Instead of writing directly to your project, the agent's file operations are redirected to a separate directory. This gives you a chance to review the diff before any changes touch your actual codebase.

Worktrees are stored in `.signal/data/worktrees/` and tracked in a JSONL manifest file. Each worktree has a unique ID (e.g., `wt_a1b2c3d4`) and a lifecycle status: `pending`, `merged`, or `discarded`.

### How isolation works

The `WorktreeProxy` wraps each agent's tool executor. It starts in passthrough mode -- read operations go directly to the real workspace. On the first file write, the proxy:

1. Creates a worktree directory (via `git worktree add` in git repos, or a full directory copy otherwise).
2. Switches to isolated mode, routing all subsequent `file_system` writes to the worktree.
3. Records the worktree in the manifest.

Non-file-system tool calls (e.g., bash, web search) always pass through to the real executor regardless of isolation state.

### Git vs. non-git workspaces

| Feature         | Git workspace                        | Non-git workspace              |
|-----------------|--------------------------------------|--------------------------------|
| Isolation       | `git worktree add` with a new branch | Full directory copy            |
| Branch name     | `signal/worktree/{name}`             | N/A                            |
| Diff            | `git diff HEAD`                      | File-by-file unified diff      |
| Changed files   | `git diff --name-only HEAD`          | SHA-256 hash comparison        |
| Cleanup         | Remove directory + `git worktree prune` + branch delete | Remove directory |

### Reviewing worktrees

List all pending worktrees:

```bash
signal worktree list
```

Output is a table showing worktree ID, agent name, creation time, number of changed files, and whether it uses git:

```
          Pending Worktrees
 ID              Agent           Created           Files  Git
 wt_a1b2c3d4     code-reviewer   2026-04-01 14:30      3  Y
 wt_e5f6a7b8     refactor-agent  2026-04-01 15:00      7  Y
```

### Merging worktree changes

To apply a worktree's changes to your workspace:

```bash
signal worktree merge wt_a1b2c3d4
```

This copies changed files from the worktree back to the workspace root, cleans up the worktree directory (and prunes the git branch if applicable), and marks the record as `merged`.

### Discarding worktree changes

To throw away a worktree without applying its changes:

```bash
signal worktree discard wt_a1b2c3d4
```

This removes the worktree directory, prunes git references, and marks the record as `discarded`.

---

## Forks

### What forks are

Forks let you explore multiple approaches to a task in parallel. Each approach runs in its own worktree, and after all branches complete, you review the results and pick the winner.

Under the hood, the `ForkRunner` dispatches each task string through the normal executor pipeline with semaphore-bounded concurrency. Each branch may produce its own worktree if it writes files.

### Running a fork

Provide at least two task descriptions as arguments:

```bash
signal fork "Refactor the parser using visitor pattern" "Refactor the parser using strategy pattern"
```

Each task string becomes an independent branch. Branches run concurrently up to the configured concurrency limit.

Output shows the result of each branch:

```
Fork complete: 2 branches

--- Branch 1: "Refactor the parser using visitor pattern" ---
Status: Success
Response: I've refactored the parser using the visitor...
Changed files: 3
Worktree: wt_a1b2c3d4

--- Branch 2: "Refactor the parser using strategy pattern" ---
Status: Success
Response: I've refactored the parser using the strategy...
Changed files: 5
Worktree: wt_e5f6a7b8

Review with: signal worktree list
Merge winner: signal worktree merge <id>
Discard rest: signal worktree discard <id>
```

### Picking a winner

After reviewing the fork output:

1. Use `signal worktree list` to see all pending worktrees.
2. Merge the winning approach: `signal worktree merge wt_a1b2c3d4`
3. Discard the losing approaches: `signal worktree discard wt_e5f6a7b8`

### Concurrency option

Override the profile's default concurrency with `--concurrency`:

```bash
signal fork --concurrency 3 "Approach A" "Approach B" "Approach C"
```

| Option                 | Description                                              |
|------------------------|----------------------------------------------------------|
| `--concurrency`, `-c`  | Max concurrent branches (0 = use profile default)        |

When set to `0` (the default), the value from the profile's `fork.max_concurrent_branches` field is used.

---

## Configuration

Fork concurrency is configured in the profile:

```yaml
fork:
  max_concurrent_branches: 2
```

| Field                    | Type | Default | Description                             |
|--------------------------|------|---------|-----------------------------------------|
| `max_concurrent_branches`| int  | `2`     | Max parallel worktree branches (min: 1) |

This value controls the semaphore that limits how many branches execute simultaneously. Higher values use more system resources but complete faster for CPU/IO-light tasks.

---

## Next steps

- [Profiles](profiles.md) -- configuring `fork.max_concurrent_branches` and other settings
- [Security](security.md) -- policy enforcement for tools used within worktrees
- [CLI Reference](cli-reference.md) -- full command reference for `signal worktree` and `signal fork`
