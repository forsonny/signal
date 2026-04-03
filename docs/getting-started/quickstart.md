# Quickstart

**What you'll learn:**

- How to initialize a Signal instance
- How to send a one-shot message with `signal talk`
- What happens inside Signal when you send a message
- How to search and inspect agent memories
- How to start an interactive conversation with `signal chat`

---

## Set your API key

If you haven't already, export your API key. The default configuration expects an Anthropic key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

See [Installation](installation.md) for other providers and persistent configuration.

---

## Initialize a Signal instance

Navigate to a project directory (or create one) and run:

```bash
mkdir my-project && cd my-project
uv run signal init
```

This creates a `.signal/` directory containing:

- `config.yaml` -- instance configuration (model, API key variable, profile name)
- `memory/` -- agent memory storage (markdown files with YAML frontmatter)
- `data/` -- runtime data, sessions, tasks, and worktrees
- `triggers/` -- static and dynamic heartbeat triggers
- `plugins/` -- custom tool plugins
- `logs/` -- runtime logs

By default, `signal init` uses the `blank` profile, which gives you a general-purpose assistant with file system, bash, and web search tools.

---

## Send a message

Use `signal talk` for one-shot interactions:

```bash
uv run signal talk "What files are in this directory?"
```

The agent processes your message and prints its response to stdout.

---

## What just happened

When you ran `signal talk`, Signal executed this pipeline:

1. **Instance discovery** -- the CLI searched the current directory and its parents for a `.signal/` directory containing a `config.yaml` file.
2. **Bootstrap** -- Signal loaded the config and profile, then wired up the agent runtime: Prime agent, message bus, tool registry, and memory engine.
3. **Execution** -- your message was sent to the Prime agent, which used its system prompt identity and available tools to generate a response.
4. **Response** -- the executor returned the agent's response text, which the CLI printed.

If the agent encountered an error (missing API key, network failure, tool error), the response would be prefixed with `Error:` instead.

---

## Working with memory

Signal agents build persistent memory over time. You can search and inspect memories from the CLI.

### Search memories

```bash
uv run signal memory search
```

Filter by tags, agent name, or memory type:

```bash
uv run signal memory search --tags "python,testing"
uv run signal memory search --agent prime
uv run signal memory search --type learning
uv run signal memory search --limit 5
```

Search results display in a table with columns for ID, agent, type, tags, confidence score, and last-updated date.

### Inspect a memory

Use a memory ID from the search results to see full details:

```bash
uv run signal memory inspect mem_a1b2c3d4
```

This shows the memory's complete metadata (agent, type, tags, confidence, version, timestamps, access count, changelog) followed by its content.

---

## Interactive chat

For multi-turn conversations, use `signal chat`:

```bash
uv run signal chat
```

This starts an interactive REPL with a new session. You'll see the session ID printed at startup. Type messages at the `you>` prompt and the agent will respond.

### Chat commands

Inside the chat REPL, these slash commands are available:

| Command     | Action                              |
|-------------|-------------------------------------|
| `/quit`     | Exit the conversation               |
| `/exit`     | Exit the conversation (alias)       |
| `/history`  | Show all turns in the current session |
| `/session`  | Print the current session ID        |

### Resume a session

To continue a previous conversation, pass the session ID:

```bash
uv run signal chat --session abc123
```

When resuming, Signal prints the last few turns as context before handing you the prompt.

### End a session

Press `Ctrl+C` or type `/quit`. The session ID is printed on exit so you can resume later.

---

## Next steps

- [Your First Profile](first-profile.md) -- create a custom profile with micro-agents
- [Core Concepts](../user-guide/concepts.md) -- understand Signal's architecture
- [CLI Reference](../user-guide/cli-reference.md) -- complete command documentation
