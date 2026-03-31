# CLI Reference

All commands are invoked via `uv run signal <command>` (or `signal <command>` if the package is installed globally).

---

## signal init

Initialize a new Signal instance in the current directory.

```
signal init [OPTIONS]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--profile TEXT` | `blank` | Profile to initialize with. Accepts a built-in profile name or a path to a `.yaml` file. |

**Behavior:**

- Creates a `.signal/` directory in the current working directory.
- Writes `config.yaml` with settings derived from the profile.
- Creates subdirectory structure for data, memory, triggers, plugins, and logs.
- Exits with an error if a `.signal/` directory already exists in the current directory.

**Examples:**

```bash
# Initialize with the built-in blank profile
uv run signal init

# Initialize with a custom profile file
uv run signal init --profile ./my-profile.yaml
```

---

## signal talk

Send a one-shot message to Signal and print the response.

```
signal talk MESSAGE
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `MESSAGE` | The message to send. Quote multi-word messages. |

**Behavior:**

- Searches for a Signal instance by walking up the directory tree from the current working directory (similar to how git locates `.git/`).
- Loads the instance config and profile.
- Sends the message to the configured LLM via LiteLLM.
- Prints the response to stdout.
- Exits with an error if no instance is found.

**Examples:**

```bash
uv run signal talk "hello"
uv run signal talk "summarize this project"
```

---

## signal memory search

Search stored memories by tags, agent, and type.

```
signal memory search [OPTIONS]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--tags TEXT` | None | Comma-separated tags to filter by. Matches memories that have at least one overlapping tag. |
| `--agent TEXT` | None | Filter to memories owned by this agent (e.g., `prime`, `code-review`). |
| `--type TEXT` | None | Filter by memory type (`identity`, `learning`, `pattern`, `outcome`, `context`, `shared`). |
| `--limit INTEGER` | `10` | Maximum number of results to return. |

**Behavior:**

- Searches the SQLite memory index for matching memories.
- Results are ranked by a composite score: tag overlap (40%), recency (30%), access frequency (20%), confidence (10%).
- Displays a table with columns: ID, Agent, Type, Tags, Confidence, Updated.
- Prints "No memories found." if no memories match the filters.

**Examples:**

```bash
# Show all memories (most recent first)
uv run signal memory search

# Search by tags
uv run signal memory search --tags "python,errors"

# Filter by agent and type
uv run signal memory search --agent prime --type identity
```

---

## signal memory inspect

View full details of a specific memory by ID.

```
signal memory inspect MEMORY_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `MEMORY_ID` | The memory ID to inspect (e.g., `mem_a8f3c291`). |

**Behavior:**

- Loads the memory from disk via the index.
- Displays all metadata fields (agent, type, tags, confidence, version, timestamps, access count, changelog) and the full content.
- Updates the memory's access statistics (accessed_at and access_count).
- Exits with an error if the memory ID is not found.

**Examples:**

```bash
uv run signal memory inspect mem_a8f3c291
```

---

## Coming in Future Phases

Many commands are planned but not yet implemented. These include agent management, session handling, heartbeat control, worktrees, forks, and more. This reference will be updated as each phase ships.
