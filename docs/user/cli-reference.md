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

## Coming in Future Phases

Many commands are planned but not yet implemented. These include agent management, memory operations, session handling, heartbeat control, worktrees, forks, and more. This reference will be updated as each phase ships.
