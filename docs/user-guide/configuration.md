# Configuration

**What you'll learn:**

- What the `.signal/` instance directory contains
- The complete `config.yaml` format and all fields
- How Signal discovers the nearest instance
- How to configure LLM models and providers
- How tool, memory, and security settings work

---

## Instance directory structure

Running `signal init` creates a `.signal/` directory with the following layout:

```
.signal/
  config.yaml          # Instance configuration
  data/
    runtime/           # Runtime state files
    sessions/          # Conversation session data
    tasks/             # Task tracking data
    worktrees/         # Worktree manifests (created by fork)
  memory/
    prime/             # Prime agent's memory files
    micro/             # Micro-agent memory files
    shared/            # Shared memory files
  triggers/
    static/            # Profile-defined triggers
    dynamic/           # Runtime-created triggers
  plugins/             # Custom tool plugins
  logs/                # Runtime logs
```

Memory files are markdown with YAML frontmatter. Session and task data are JSON. The `config.yaml` file is the only file you typically edit by hand.

---

## config.yaml format

The `config.yaml` file is generated at `signal init` time and controls instance-level settings. Here is the full format with defaults:

```yaml
profile_name: blank

ai:
  default_model: "anthropic/claude-sonnet-4-20250514"
  api_key_env: "ANTHROPIC_API_KEY"

tools:
  max_iterations: 20
```

### Top-level fields

| Field          | Type   | Required | Description                                          |
|----------------|--------|----------|------------------------------------------------------|
| `profile_name` | string | yes      | Name or path of the profile to load at boot time     |
| `ai`           | object | no       | AI layer settings (model and API key)                |
| `tools`        | object | no       | Global tool execution settings                       |

### ai section

Controls which LLM model Signal uses and where to find the API key.

| Field           | Type   | Default                              | Description                                     |
|-----------------|--------|--------------------------------------|-------------------------------------------------|
| `default_model` | string | `"anthropic/claude-sonnet-4-20250514"` | LiteLLM model identifier                        |
| `api_key_env`   | string | `"ANTHROPIC_API_KEY"`                | Environment variable name holding the API key   |

The `default_model` value is passed directly to [LiteLLM](https://docs.litellm.ai/docs/providers), so any model string LiteLLM recognizes works here. Examples:

```yaml
# Anthropic
ai:
  default_model: "anthropic/claude-sonnet-4-20250514"
  api_key_env: "ANTHROPIC_API_KEY"

# OpenAI
ai:
  default_model: "openai/gpt-4o"
  api_key_env: "OPENAI_API_KEY"

# Azure OpenAI
ai:
  default_model: "azure/gpt-4o"
  api_key_env: "AZURE_API_KEY"

# Local via Ollama
ai:
  default_model: "ollama/llama3"
  api_key_env: "OLLAMA_API_KEY"
```

### tools section

Global tool execution settings that apply as a cap on all agents.

| Field            | Type | Default | Description                                        |
|------------------|------|---------|----------------------------------------------------|
| `max_iterations` | int  | `20`    | Global max agentic loop iterations (min: 1)        |

This value caps the per-agent `max_iterations` setting from the profile. If an agent's profile sets `max_iterations: 50` but the global config sets `max_iterations: 20`, the agent is limited to 20 iterations.

---

## Instance discovery

When you run any Signal command (except `signal init`), the CLI searches for a `.signal/` directory by walking up the filesystem from your current working directory.

The algorithm:

1. Check if `<current_dir>/.signal/` exists and contains a `config.yaml` file.
2. If not found, move to the parent directory and repeat.
3. Continue until the filesystem root is reached.
4. If no instance is found, exit with an error: `"No Signal instance found. Run 'signal init' to create one."`

This means you can run `signal talk` or `signal chat` from any subdirectory of your project -- Signal will find the `.signal/` directory in any ancestor.

---

## Model selection

Signal delegates all LLM calls to LiteLLM. To switch providers:

1. Edit `.signal/config.yaml` and set `ai.default_model` to the desired LiteLLM model string.
2. Set `ai.api_key_env` to the name of the environment variable holding the key for that provider.
3. Export the environment variable in your shell.

```bash
# Example: switch to OpenAI
export OPENAI_API_KEY="sk-..."
```

```yaml
# .signal/config.yaml
ai:
  default_model: "openai/gpt-4o"
  api_key_env: "OPENAI_API_KEY"
```

The model change takes effect on the next `signal talk` or `signal chat` invocation. No restart or re-init is needed.

---

## Tool configuration

Tool availability is controlled at two levels:

1. **Profile level** -- the `plugins.available` list declares which tool plugins are loaded at bootstrap. Only these tools exist in the runtime.
2. **Agent level** -- each micro-agent's `plugins` list declares which of the available tools it can use.
3. **Global cap** -- the `tools.max_iterations` value in `config.yaml` caps the maximum agentic loop iterations for any agent.

If a tool is not in `plugins.available`, no agent can use it regardless of their individual `plugins` list.

---

## Memory configuration

Memory behavior is tuned in the profile's `memory` section (not in `config.yaml`):

| Field                  | Type        | Default | Description                                              |
|------------------------|-------------|---------|----------------------------------------------------------|
| `decay_half_life_days` | int         | `30`    | Days after which memory relevance is halved (min: 1)     |
| `embedding_model`      | string/null | `null`  | LiteLLM model ID for embeddings, or null to disable      |

When `embedding_model` is set, semantic search is available in addition to tag and type filtering. When null, only metadata-based search works.

The optional `memory_keeper` section in the profile configures automatic memory maintenance:

| Field                      | Type  | Default       | Description                                         |
|----------------------------|-------|---------------|-----------------------------------------------------|
| `schedule`                 | string| `"0 3 * * 0"` | Cron expression for maintenance runs                |
| `staleness_threshold_days` | int   | `90`          | Days without access before a memory is stale        |
| `min_confidence`           | float | `0.1`         | Effective confidence below which stale memories are archived |
| `max_candidates_per_run`   | int   | `20`          | Max memory groups to process per maintenance run    |

---

## Security configuration

Security policies are defined in the profile's `security.policies` list. Each policy entry targets a specific agent:

```yaml
security:
  policies:
    - agent: python-reviewer
      allow_tools: [file_system]
      allow_memory_read: [prime, python-reviewer]
```

| Field              | Type           | Default | Description                                          |
|--------------------|----------------|---------|------------------------------------------------------|
| `agent`            | string         | required| Agent name this policy applies to                    |
| `allow_tools`      | list[str]/null | `null`  | Allowed tool names, or null for unrestricted access   |
| `allow_memory_read`| list[str]/null | `null`  | Allowed memory agent scopes, or null for unrestricted |

When a field is `null` (or omitted), the agent has unrestricted access. When it is an empty list `[]`, the agent has no access at all.

---

## Next steps

- [Profiles](profiles.md) -- complete profile YAML schema reference
- [CLI Reference](cli-reference.md) -- every command with syntax and examples
- [Your First Profile](../getting-started/first-profile.md) -- hands-on profile creation walkthrough
