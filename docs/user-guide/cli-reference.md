# CLI Reference

**What you'll learn:**

- Every Signal CLI command with its syntax, arguments, and options
- Behavior details and exit codes
- Practical examples for each command

Signal's CLI entry point is `signal`. All commands require the `signalagent` package to be installed. When using a development checkout, prefix commands with `uv run`.

---

## Global behavior

The `signal` CLI is built with [Typer](https://typer.tiangolo.com/) and uses [Rich](https://rich.readthedocs.io/) for formatted output. Running `signal` with no arguments displays help text.

Most commands require a Signal instance (a `.signal/` directory with a `config.yaml` file). Instance discovery walks up the directory tree from the current working directory, so you can run commands from any subdirectory of an initialized project. If no instance is found, the command exits with code 1 and prints an error message.

---

## signal init

Initialize a new Signal instance in the current directory.

**Syntax:**

```
signal init [OPTIONS]
```

**Options:**

| Option      | Type   | Default   | Description                          |
|-------------|--------|-----------|--------------------------------------|
| `--profile` | string | `"blank"` | Profile to initialize with           |

**Behavior:**

1. Resolves the profile by name or file path. If the value is a path to an existing `.yaml`/`.yml` file, it is loaded directly. Otherwise, Signal looks for a built-in profile with that name.
2. Creates the `.signal/` directory in the current working directory.
3. Creates subdirectories: `data/`, `data/runtime/`, `data/sessions/`, `data/tasks/`, `memory/`, `memory/prime/`, `memory/micro/`, `memory/shared/`, `triggers/`, `triggers/static/`, `triggers/dynamic/`, `plugins/`, `logs/`.
4. Writes `config.yaml` with the profile name and default AI/tool settings.

**Exit codes:**

- `0` -- success
- `1` -- invalid profile name or instance already exists

**Examples:**

```bash
# Initialize with the default blank profile
uv run signal init

# Initialize with a custom profile file
uv run signal init --profile ./my-profile.yaml

# Initialize with a named built-in profile
uv run signal init --profile blank
```

---

## signal talk

Send a one-shot message to Signal and print the response.

**Syntax:**

```
signal talk MESSAGE
```

**Arguments:**

| Argument  | Type   | Required | Description            |
|-----------|--------|----------|------------------------|
| `MESSAGE` | string | yes      | Message to send        |

**Behavior:**

1. Finds the nearest Signal instance by searching up the directory tree.
2. Loads config and profile, bootstraps the runtime (agent host, message bus, tool registry, memory engine).
3. Sends the message to the Prime agent's executor.
4. Prints the agent's response to stdout.
5. If the agent encounters an error, the output is prefixed with `Error:`.

**Exit codes:**

- `0` -- success (including when the agent returns an error response)
- `1` -- no Signal instance found

**Examples:**

```bash
uv run signal talk "What files are in this directory?"
uv run signal talk "Summarize the README.md file"
uv run signal talk "Write a Python function that sorts a list of dictionaries by key"
```

---

## signal chat

Start an interactive multi-turn conversation.

**Syntax:**

```
signal chat [OPTIONS]
```

**Options:**

| Option               | Short | Type   | Default | Description                   |
|----------------------|-------|--------|---------|-------------------------------|
| `--session`          | `-s`  | string | None    | Resume a session by ID        |

**Behavior:**

1. Finds the nearest Signal instance.
2. If `--session` is provided and the session exists, resumes it (prints the last few turns as context). Otherwise, creates a new session and prints its ID.
3. Enters a REPL loop with a `you>` prompt.
4. User input is sent to the agent executor with the session ID for context continuity.
5. Agent responses are printed below the prompt.
6. Slash commands are handled locally (not sent to the agent).
7. On exit (`/quit`, `/exit`, `Ctrl+C`, or EOF), the session ID is printed.

**REPL commands:**

| Command     | Action                              |
|-------------|-------------------------------------|
| `/quit`     | Exit the conversation               |
| `/exit`     | Exit the conversation               |
| `/history`  | Show all turns in the current session |
| `/session`  | Print the current session ID        |

**Exit codes:**

- `0` -- normal exit
- `1` -- no Signal instance found

**Examples:**

```bash
# Start a new conversation
uv run signal chat

# Resume a previous session
uv run signal chat --session abc123def
uv run signal chat -s abc123def
```

---

## signal fork

Run multiple approaches in parallel worktrees.

**Syntax:**

```
signal fork TASKS... [OPTIONS]
```

**Arguments:**

| Argument | Type       | Required | Description                                    |
|----------|------------|----------|------------------------------------------------|
| `TASKS`  | string(s)  | yes      | Task descriptions, one per branch (minimum 2)  |

**Options:**

| Option          | Short | Type | Default | Description                                      |
|-----------------|-------|------|---------|--------------------------------------------------|
| `--concurrency` | `-c`  | int  | `0`     | Max concurrent branches (0 = use profile default) |

**Behavior:**

1. Validates that at least 2 task descriptions were provided.
2. Finds the nearest Signal instance and bootstraps the runtime.
3. Creates a worktree branch for each task and runs them concurrently (up to `--concurrency` or the profile's `fork.max_concurrent_branches`).
4. Prints results for each branch: status (success/failed), a response preview, changed file count, and worktree ID.
5. Prints instructions for reviewing results with `signal worktree` commands.

**Exit codes:**

- `0` -- at least one branch succeeded
- `1` -- all branches failed, fewer than 2 tasks, or no instance found

**Examples:**

```bash
# Run two approaches in parallel
uv run signal fork "Implement sorting with quicksort" "Implement sorting with mergesort"

# Limit concurrency to 1 (sequential execution)
uv run signal fork "Approach A" "Approach B" "Approach C" --concurrency 1
```

---

## signal memory

Search and inspect agent memories. This is a command group with subcommands.

**Syntax:**

```
signal memory COMMAND [OPTIONS]
```

Running `signal memory` with no subcommand displays help.

### signal memory search

Search memories by tags, agent, and type.

**Syntax:**

```
signal memory search [OPTIONS]
```

**Options:**

| Option   | Type   | Default | Description                       |
|----------|--------|---------|-----------------------------------|
| `--tags` | string | None    | Comma-separated tags to filter by |
| `--agent`| string | None    | Filter by agent name              |
| `--type` | string | None    | Filter by memory type             |
| `--limit`| int    | `10`    | Maximum results to return         |

**Behavior:**

Searches the memory engine and displays results in a table with columns: ID, Agent, Type, Tags, Confidence, Updated.

**Memory types:** `identity`, `learning`, `pattern`, `outcome`, `context`, `shared`

**Examples:**

```bash
# Search all memories
uv run signal memory search

# Filter by tags
uv run signal memory search --tags "python,testing"

# Filter by agent and type
uv run signal memory search --agent prime --type learning

# Limit results
uv run signal memory search --limit 5
```

### signal memory inspect

Inspect a specific memory by ID.

**Syntax:**

```
signal memory inspect MEMORY_ID
```

**Arguments:**

| Argument    | Type   | Required | Description            |
|-------------|--------|----------|------------------------|
| `MEMORY_ID` | string | yes      | Memory ID to inspect   |

**Behavior:**

Loads the memory by ID and prints its full metadata: ID, agent, type, tags, confidence, version, created/updated/accessed timestamps, access count, and changelog. The memory's content is printed last.

**Exit codes:**

- `0` -- success
- `1` -- no instance found or memory not found

**Examples:**

```bash
uv run signal memory inspect mem_a1b2c3d4
```

---

## signal sessions

Manage conversation sessions. This is a command group with subcommands.

**Syntax:**

```
signal sessions COMMAND [OPTIONS]
```

Running `signal sessions` with no subcommand displays help.

### signal sessions list

List recent conversation sessions.

**Syntax:**

```
signal sessions list [OPTIONS]
```

**Options:**

| Option    | Short | Type | Default | Description              |
|-----------|-------|------|---------|--------------------------|
| `--limit` | `-n`  | int  | `20`    | Max sessions to show     |

**Behavior:**

Lists sessions in a table with columns: ID, Created, Preview, Turns. The preview shows the first 60 characters of the first user message. Sessions are stored in `.signal/data/sessions/`.

**Examples:**

```bash
# List recent sessions
uv run signal sessions list

# Show only the last 5 sessions
uv run signal sessions list --limit 5
uv run signal sessions list -n 5
```

---

## signal worktree

Manage agent worktrees created by `signal fork`. This is a command group with subcommands.

**Syntax:**

```
signal worktree COMMAND [ARGUMENTS]
```

Running `signal worktree` with no subcommand displays help.

### signal worktree list

List pending worktrees awaiting review.

**Syntax:**

```
signal worktree list
```

**Behavior:**

Displays a table of worktrees in "pending" status with columns: ID, Agent, Created, Files (changed file count), Git (Y/N for whether the worktree uses a git branch).

**Examples:**

```bash
uv run signal worktree list
```

### signal worktree merge

Merge worktree changes into the workspace.

**Syntax:**

```
signal worktree merge WORKTREE_ID
```

**Arguments:**

| Argument       | Type   | Required | Description            |
|----------------|--------|----------|------------------------|
| `WORKTREE_ID`  | string | yes      | Worktree ID to merge   |

**Behavior:**

Copies changed files from the worktree back to the original workspace, cleans up the worktree directory and git branch, and marks the worktree record as "merged".

**Exit codes:**

- `0` -- success
- `1` -- worktree not found or not in pending state

**Examples:**

```bash
uv run signal worktree merge wt_a1b2c3d4
```

### signal worktree discard

Discard worktree changes without merging.

**Syntax:**

```
signal worktree discard WORKTREE_ID
```

**Arguments:**

| Argument       | Type   | Required | Description              |
|----------------|--------|----------|--------------------------|
| `WORKTREE_ID`  | string | yes      | Worktree ID to discard   |

**Behavior:**

Removes the worktree directory and git branch, and marks the worktree record as "discarded". No files are copied back to the workspace.

**Exit codes:**

- `0` -- success
- `1` -- worktree not found or not in pending state

**Examples:**

```bash
uv run signal worktree discard wt_a1b2c3d4
```

---

## Next steps

- [Configuration](configuration.md) -- config.yaml format and all fields
- [Profiles](profiles.md) -- complete profile YAML schema
- [Core Concepts](concepts.md) -- understand the architecture behind these commands
