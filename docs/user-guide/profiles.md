# Profiles

**What you'll learn:**

- What profiles are and when they are applied
- The complete YAML schema with all fields documented
- How to use the built-in blank profile
- How to write custom profiles
- Detailed configuration for micro-agents, hooks, heartbeat, fork, memory, and security

---

## What profiles are

A profile is a YAML file that defines the full shape of a Signal instance. It is applied once at `signal init` time. The profile name is stored in `.signal/config.yaml` under the `profile_name` field, and the profile is re-loaded from that reference every time the runtime boots (on each `signal talk`, `signal chat`, or `signal fork` invocation).

Profiles control:

- The Prime agent's system-prompt identity
- Which micro-agents exist, their skills, and their permissions
- Which tool plugins are available
- Which hooks are active
- Heartbeat triggers (cron schedules and file watchers)
- Fork execution concurrency
- Memory decay and embedding settings
- Optional MemoryKeeper agent scheduling
- Per-agent security policies

---

## Profile resolution

When Signal loads a profile (by name or path), it follows this resolution order:

1. If the value is a path to an existing `.yaml` or `.yml` file on disk, load it directly.
2. Otherwise, look for a built-in profile named `<value>.yaml` in the `signalagent/profiles/` package directory.
3. If neither is found, raise an error.

---

## Full YAML schema

Below is the complete profile schema with every field, its type, default, and description.

### Root fields

```yaml
name: my-profile                    # string, required -- profile name
description: What this profile does # string, default: ""
version: 1.0.0                      # string, default: "1.0.0"
author: your-name                   # string, default: ""
```

| Field         | Type   | Default   | Description                                  |
|---------------|--------|-----------|----------------------------------------------|
| `name`        | string | required  | Profile name, used for display and lookup    |
| `description` | string | `""`      | Human-readable profile description           |
| `version`     | string | `"1.0.0"` | Semantic version of this profile             |
| `author`      | string | `""`      | Profile author name or identifier            |

### prime

Configures the Prime agent's system-prompt identity.

```yaml
prime:
  identity: >
    You are a helpful AI assistant. The user will define
    your purpose and add specialist agents over time.
```

| Field      | Type   | Default                                      | Description                    |
|------------|--------|----------------------------------------------|--------------------------------|
| `identity` | string | `"You are a helpful AI assistant. The user will define your purpose and add specialist agents over time."` | System prompt identity for Prime |

### micro_agents

A list of micro-agent definitions. Each entry creates a specialist agent at boot time.

```yaml
micro_agents:
  - name: code-reviewer
    skill: Analyze code for correctness, style, and security.
    talks_to: [test-runner]
    plugins: [file_system, bash]
    mcp_servers: []
    scripts: []
    can_spawn_subs: false
    max_iterations: 10
```

| Field            | Type       | Default | Description                                           |
|------------------|------------|---------|-------------------------------------------------------|
| `name`           | string     | required| Unique agent name used for routing and memory scoping |
| `skill`          | string     | required| One-line description of what this agent does          |
| `talks_to`       | list[str]  | `[]`   | Agent names this agent can send messages to           |
| `plugins`        | list[str]  | `[]`   | Tool plugin names this agent can use                  |
| `mcp_servers`    | list[str]  | `[]`   | MCP server names this agent connects to               |
| `scripts`        | list[str]  | `[]`   | Script paths this agent can execute                   |
| `can_spawn_subs` | bool       | `false`| Whether this agent can spawn sub-agents               |
| `max_iterations` | int        | `10`   | Max agentic loop iterations (min: 1)                  |

**Routing:** The `talks_to` field is a list of agent names this micro-agent is allowed to message via the message bus. Prime can always message any agent. If a micro-agent needs to delegate to another micro-agent, both must be listed in each other's `talks_to` or the message will be rejected.

**Tool access:** The `plugins` field restricts which tools from the global `plugins.available` list this agent can use. An empty list means no tool access.

### plugins

Declares which tool plugins are loaded at bootstrap.

```yaml
plugins:
  available: [file_system, bash, web_search]
```

| Field       | Type      | Default | Description                               |
|-------------|-----------|---------|-------------------------------------------|
| `available` | list[str] | `[]`   | Tool plugin names to load at startup      |

Only plugins listed here are available in the runtime. Individual agents further restrict their access via their own `plugins` field.

### hooks

Configures instance-wide tool call interception.

```yaml
hooks:
  active: [audit_log, rate_limiter]
```

| Field    | Type      | Default | Description                          |
|----------|-----------|---------|--------------------------------------|
| `active` | list[str] | `[]`   | Hook names to activate at startup    |

Hooks run before and/or after every tool call across all agents. They enable logging, policy enforcement, rate limiting, and other cross-cutting concerns.

### heartbeat

Defines triggers that fire messages into the agent system autonomously.

```yaml
heartbeat:
  clock_triggers:
    - name: daily-check
      cron: "0 9 * * *"
      recipient: prime
      payload: "Run the daily check."
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
  event_triggers:
    - name: src-watcher
      path: "./src"
      interval_seconds: 30
      recipient: code-reviewer
      payload: "Files changed: {changed_files}"
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
```

#### clock_triggers

Cron-based recurring triggers. Each trigger fires when the current minute matches its cron expression.

| Field       | Type   | Default | Description                                              |
|-------------|--------|---------|----------------------------------------------------------|
| `name`      | string | required| Unique trigger identifier                                |
| `cron`      | string | required| 5-field cron expression (minute hour dom month dow)      |
| `recipient` | string | required| Agent name to receive the trigger message                |
| `payload`   | string | `""`   | Message content sent on fire                             |
| `guards`    | object | defaults| Safety guards (see below)                                |

#### event_triggers

Polling-based file change triggers. Each trigger checks for file changes at a configurable interval.

| Field              | Type   | Default | Description                                               |
|--------------------|--------|---------|-----------------------------------------------------------|
| `name`             | string | required| Unique trigger identifier                                 |
| `path`             | string | `"."`  | Directory to watch for changes                            |
| `interval_seconds` | int    | `30`   | Seconds between polling checks (min: 5)                   |
| `recipient`        | string | required| Agent name to receive the trigger message                 |
| `payload`          | string | `""`   | Message content; use `{changed_files}` for substitution   |
| `guards`           | object | defaults| Safety guards (see below)                                 |

#### guards (shared by both trigger types)

| Field               | Type | Default | Description                                            |
|---------------------|------|---------|--------------------------------------------------------|
| `cooldown_seconds`  | int  | `60`   | Minimum seconds between consecutive fires (min: 0)     |
| `max_fires`         | int  | `0`    | Maximum total fires before auto-disable (0 = unlimited)|
| `error_threshold`   | int  | `3`    | Consecutive dispatch errors before auto-disable (min: 1)|

### fork

Controls parallel approach exploration via worktrees.

```yaml
fork:
  max_concurrent_branches: 2
```

| Field                    | Type | Default | Description                             |
|--------------------------|------|---------|-----------------------------------------|
| `max_concurrent_branches`| int  | `2`    | Max parallel worktree branches (min: 1) |

This value is used as the default when `signal fork` is run without `--concurrency`.

### memory

Tunes memory retrieval decay and optional semantic search.

```yaml
memory:
  decay_half_life_days: 30
  embedding_model: null
```

| Field                  | Type        | Default | Description                                         |
|------------------------|-------------|---------|-----------------------------------------------------|
| `decay_half_life_days` | int         | `30`   | Days after which memory relevance is halved (min: 1)|
| `embedding_model`      | string/null | `null` | LiteLLM model ID for embeddings, or null to disable |

When `embedding_model` is set (e.g., `"openai/text-embedding-3-small"`), memories are embedded at write time and semantic search becomes available alongside tag and type filtering.

### memory_keeper

Optional MemoryKeeper agent configuration. When present (not null), a maintenance agent is registered and scheduled via the heartbeat system.

```yaml
memory_keeper:
  schedule: "0 3 * * 0"
  staleness_threshold_days: 90
  min_confidence: 0.1
  max_candidates_per_run: 20
```

| Field                      | Type  | Default       | Description                                               |
|----------------------------|-------|---------------|-----------------------------------------------------------|
| `schedule`                 | string| `"0 3 * * 0"` | Cron expression for maintenance runs                      |
| `staleness_threshold_days` | int   | `90`          | Days without access before a memory is considered stale   |
| `min_confidence`           | float | `0.1`         | Effective confidence below which stale memories are archived |
| `max_candidates_per_run`   | int   | `20`          | Max memory groups to process per maintenance run          |

Set `memory_keeper` to `null` (or omit it entirely) to disable automatic memory maintenance.

### security

Declarative per-agent allow-list policies.

```yaml
security:
  policies:
    - agent: code-reviewer
      allow_tools: [file_system]
      allow_memory_read: [prime, code-reviewer]
    - agent: test-runner
      allow_tools: [bash]
      allow_memory_read: []
```

| Field      | Type             | Default | Description                      |
|------------|------------------|---------|----------------------------------|
| `policies` | list[AgentPolicy]| `[]`   | Per-agent security policies      |

Each policy entry:

| Field              | Type           | Default | Description                                           |
|--------------------|----------------|---------|-------------------------------------------------------|
| `agent`            | string         | required| Agent name this policy applies to                     |
| `allow_tools`      | list[str]/null | `null` | Allowed tool names, or null for unrestricted access    |
| `allow_memory_read`| list[str]/null | `null` | Allowed memory agent scopes, or null for unrestricted  |

**null vs empty list:** A `null` value (or omitted field) means the agent has unrestricted access. An empty list `[]` means the agent has zero access. This distinction is important -- omitting `allow_tools` gives full tool access, while setting `allow_tools: []` blocks all tools.

---

## Built-in blank profile

Signal ships with one built-in profile called `blank`. It provides a minimal starting point:

```yaml
name: blank
description: Empty Signal instance -- build your own
version: 1.0.0

prime:
  identity: >
    You are a helpful AI assistant. The user will define
    your purpose and add specialist agents over time.

micro_agents: []

plugins:
  available: [file_system, bash, web_search]

heartbeat:
  clock_triggers: []
  event_triggers: []

fork:
  max_concurrent_branches: 2

memory:
  decay_half_life_days: 30
```

No micro-agents, no hooks, no heartbeat triggers, no security policies, no MemoryKeeper. The Prime agent has access to file_system, bash, and web_search tools.

---

## Custom profiles

To create a custom profile:

1. Create a `.yaml` file anywhere on disk.
2. Set the `name` field to a unique identifier.
3. Define your Prime identity, micro-agents, plugins, and other sections.
4. Pass the file path to `signal init`:

```bash
uv run signal init --profile ./my-profile.yaml
```

See [Your First Profile](../getting-started/first-profile.md) for a step-by-step walkthrough.

### Schema validation

All profile fields use Pydantic v2 with `extra="forbid"`, meaning:

- Unknown fields cause a validation error at load time.
- Required fields that are missing cause a validation error.
- Type mismatches (e.g., a string where an int is expected) cause a validation error.

This strict validation catches configuration errors early rather than at runtime.

---

## Next steps

- [Your First Profile](../getting-started/first-profile.md) -- hands-on profile creation walkthrough
- [Configuration](configuration.md) -- instance-level config.yaml reference
- [Core Concepts](concepts.md) -- how agents, memory, and the message bus interact
