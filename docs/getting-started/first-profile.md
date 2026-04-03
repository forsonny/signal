# Your First Profile

**What you'll learn:**

- What a Signal profile is and how it configures an instance
- How to use the built-in blank profile as a starting point
- How to create a custom YAML profile with micro-agents
- How to add hooks and heartbeat triggers
- How to initialize an instance with your custom profile

---

## What is a profile?

A profile is a YAML manifest that defines what a Signal instance becomes at initialization time. It specifies:

- The Prime agent's identity (system prompt)
- Micro-agents and their skills, routing, and tool access
- Tool plugins to load
- Hooks to activate
- Heartbeat triggers (cron schedules and file watchers)
- Fork execution limits
- Memory configuration
- Security policies

Profiles are applied once, at `signal init` time. The profile name is stored in `.signal/config.yaml` and referenced at every subsequent boot to reconstruct the runtime.

---

## The blank profile

Signal ships with a built-in `blank` profile. When you run `signal init` without specifying a profile, this is what gets used. Here is its complete content:

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

This gives you a general-purpose Prime agent with file system, bash, and web search tools, no micro-agents, and no heartbeat triggers. It is a clean slate.

---

## Create a custom profile

Let's build a profile for a code review assistant with a dedicated micro-agent for Python analysis.

### Step 1: Create the YAML file

Create a file called `code-reviewer.yaml` in your project directory:

```yaml
name: code-reviewer
description: Code review assistant with Python specialist
version: 1.0.0
author: your-name

prime:
  identity: >
    You are a senior code reviewer. When the user submits code or asks for
    a review, delegate Python-specific analysis to the python-reviewer agent.
    Synthesize results into clear, actionable feedback.

micro_agents:
  - name: python-reviewer
    skill: >
      Analyze Python code for correctness, style (PEP 8), type safety,
      performance, and security vulnerabilities. Return structured findings.
    talks_to: []
    plugins: [file_system]
    mcp_servers: []
    scripts: []
    can_spawn_subs: false
    max_iterations: 10

plugins:
  available: [file_system, bash]

hooks:
  active: []

heartbeat:
  clock_triggers: []
  event_triggers: []

fork:
  max_concurrent_branches: 2

memory:
  decay_half_life_days: 30
```

### Step 2: Understand the micro-agent fields

Each micro-agent entry supports these fields:

| Field             | Type       | Default | Description                                      |
|-------------------|------------|---------|--------------------------------------------------|
| `name`            | string     | required | Unique agent name for routing and memory scoping |
| `skill`           | string     | required | One-line description of what the agent does      |
| `talks_to`        | list[str]  | `[]`    | Names of agents this agent can message           |
| `plugins`         | list[str]  | `[]`    | Tool plugin names the agent can use              |
| `mcp_servers`     | list[str]  | `[]`    | MCP server names the agent connects to           |
| `scripts`         | list[str]  | `[]`    | Script paths the agent can execute               |
| `can_spawn_subs`  | bool       | `false` | Whether the agent can spawn sub-agents           |
| `max_iterations`  | int        | `10`    | Maximum agentic loop iterations (min: 1)         |

---

## Add hooks

Hooks intercept every tool call for logging, policy enforcement, or side effects. Activate them by name in the `hooks` section:

```yaml
hooks:
  active: [audit_log, rate_limiter]
```

Hooks run before and after every tool invocation across all agents in the instance.

---

## Add heartbeat triggers

Heartbeat triggers fire messages into the agent system on a schedule or in response to file changes.

### Clock triggers (cron)

A clock trigger uses a 5-field cron expression (minute, hour, day-of-month, month, day-of-week):

```yaml
heartbeat:
  clock_triggers:
    - name: daily-review-reminder
      cron: "0 9 * * 1-5"
      recipient: prime
      payload: "Check for new pull requests to review."
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
  event_triggers: []
```

### File event triggers

A file event trigger polls a directory for changes at a configurable interval:

```yaml
heartbeat:
  clock_triggers: []
  event_triggers:
    - name: src-watcher
      path: "./src"
      interval_seconds: 30
      recipient: python-reviewer
      payload: "Files changed: {changed_files}"
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
```

The `{changed_files}` placeholder is replaced with a comma-separated list of changed file paths when the trigger fires.

### Trigger guards

Both trigger types support safety guards:

| Field               | Default | Description                                           |
|---------------------|---------|-------------------------------------------------------|
| `cooldown_seconds`  | `60`    | Minimum seconds between consecutive fires             |
| `max_fires`         | `0`     | Maximum total fires before auto-disable (0 = unlimited) |
| `error_threshold`   | `3`     | Consecutive dispatch errors before auto-disable       |

---

## Initialize with your profile

Pass the profile file path to `signal init`:

```bash
uv run signal init --profile code-reviewer.yaml
```

Signal resolves profiles in this order:

1. If the value is a path to an existing `.yaml` or `.yml` file, load it directly.
2. Otherwise, look for a built-in profile with that name under `signalagent/profiles/`.

After initialization, verify the instance was created:

```bash
ls .signal/
```

You should see `config.yaml`, `memory/`, `data/`, `triggers/`, `plugins/`, and `logs/`.

---

## Verify the agent works

Send a test message to confirm the Prime agent is using the correct identity:

```bash
uv run signal talk "What is your role and what specialist agents do you have?"
```

The Prime agent should describe itself as a code reviewer and mention the `python-reviewer` micro-agent.

---

## Complete example

Here is the full `code-reviewer.yaml` profile with all sections populated:

```yaml
name: code-reviewer
description: Code review assistant with Python specialist
version: 1.0.0
author: your-name

prime:
  identity: >
    You are a senior code reviewer. When the user submits code or asks for
    a review, delegate Python-specific analysis to the python-reviewer agent.
    Synthesize results into clear, actionable feedback.

micro_agents:
  - name: python-reviewer
    skill: >
      Analyze Python code for correctness, style (PEP 8), type safety,
      performance, and security vulnerabilities. Return structured findings.
    talks_to: []
    plugins: [file_system]
    mcp_servers: []
    scripts: []
    can_spawn_subs: false
    max_iterations: 10

plugins:
  available: [file_system, bash]

hooks:
  active: []

heartbeat:
  clock_triggers:
    - name: daily-review-reminder
      cron: "0 9 * * 1-5"
      recipient: prime
      payload: "Check for new pull requests to review."
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
  event_triggers:
    - name: src-watcher
      path: "./src"
      interval_seconds: 30
      recipient: python-reviewer
      payload: "Files changed: {changed_files}"
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3

fork:
  max_concurrent_branches: 2

memory:
  decay_half_life_days: 30

security:
  policies: []
```

---

## Next steps

- [Core Concepts](../user-guide/concepts.md) -- understand how agents, memory, and the message bus work together
- [Profiles Reference](../user-guide/profiles.md) -- complete schema documentation for all profile fields
- [Configuration](../user-guide/configuration.md) -- instance-level config.yaml reference
