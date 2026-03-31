# Profiles

## What Profiles Are

A profile is a YAML manifest that defines what a Signal instance becomes. It sets the Prime agent's identity, declares which micro-agents exist, and lists which plugins are available. Two instances initialized from the same profile start identical; they diverge only as they accumulate memory and configuration changes over time.

Profiles are applied once at `signal init`. Changing a profile file after init does not affect an existing instance.

## Built-in Profiles

### blank

The only built-in profile in Phase 1.

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
```

The `blank` profile creates a general-purpose assistant with no specialist agents. It is the right starting point when you want to define your own purpose.

## Profile Format

```yaml
name: string              # Required. Unique profile identifier.
description: string       # Optional. Human-readable summary.
version: string           # Optional. Semver string, default "1.0.0".
author: string            # Optional. Profile author.

prime:
  identity: string        # The system prompt / identity for the Prime agent.

micro_agents:             # List of specialist agent definitions.
  - name: string          # Required. Unique agent name within the profile.
    skill: string         # Required. Skill identifier this agent uses.
    talks_to: [string]    # Other agents this agent can delegate to.
    plugins: [string]     # Plugin identifiers available to this agent.
    mcp_servers: [string] # MCP server identifiers (Phase 4+).
    scripts: [string]     # Startup scripts (Phase 4+).
    can_spawn_subs: bool  # Whether this agent can create sub-agents. Default false.

plugins:
  available: [string]     # Plugin identifiers available to the instance.
```

## Custom Profiles

Create a YAML file following the format above, then pass its path to `signal init`:

```bash
uv run signal init --profile ./my-profile.yaml
```

The path can be relative or absolute. Signal resolves it at init time and copies `profile_name` into `config.yaml`.

**Example custom profile:**

```yaml
name: researcher
description: Focused on web research and document summarization
version: 1.0.0

prime:
  identity: >
    You are a research assistant. Your job is to find, synthesize,
    and summarize information clearly and accurately.

micro_agents: []

plugins:
  available: [web_search, file_system]
```

## Future Profiles

Later phases will introduce purpose-built profiles:

- **devtools** -- software development with code agents, shell access, and file system tools
- **writer** -- long-form writing with document structure agents
- **business** -- task management, scheduling, and communication workflows

These will ship as built-in profiles alongside the phases that implement their required capabilities.
