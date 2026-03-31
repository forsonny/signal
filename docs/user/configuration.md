# Configuration

## Instance Directory Structure

Running `signal init` creates a `.signal/` directory in your current working directory. Its layout:

```
.signal/
  config.yaml          # Instance configuration
  data/
    runtime/           # Transient runtime state
    sessions/          # Session records (Phase 6+)
    tasks/             # Task queue (Phase 3+)
  memory/
    prime/             # Prime agent memories, organized by type subdirectory
    micro/             # Micro-agent memories, organized by agent/type subdirectory
    shared/            # Cross-agent shared memories
    index.db           # SQLite metadata index for fast memory retrieval
  triggers/
    static/            # Static trigger definitions (Phase 7+)
    dynamic/           # Dynamic trigger definitions (Phase 7+)
  plugins/             # Installed plugin data (Phase 4+)
  logs/                # Log files
```

The `memory/` directory is active as of Phase 2. Memories are stored as individual markdown files with YAML frontmatter. The SQLite index (`index.db`) stores metadata for fast tag and recency-based search -- content stays in the files.

## config.yaml Format

Signal reads `config.yaml` on every `talk` invocation. The file uses YAML and supports the following fields:

```yaml
profile_name: blank

ai:
  default_model: anthropic/claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
```

| Field | Type | Description |
|-------|------|-------------|
| `profile_name` | string | The profile this instance was initialized with. Used to load the correct identity and agent definitions. |
| `ai.default_model` | string | The LiteLLM model string to use for all LLM calls. |
| `ai.api_key_env` | string | The environment variable Signal reads for the API key. |

Extra fields are not allowed -- Signal will error if `config.yaml` contains unknown keys.

## Instance Discovery

`signal talk` does not require you to be in the exact directory where you ran `signal init`. It walks up the directory tree from your current working directory, looking for a `.signal/` directory that contains a `config.yaml` file. This is the same pattern git uses to locate `.git/`.

If no instance is found after reaching the filesystem root, Signal exits with an error.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Default API key variable for Anthropic models. |

Signal reads the environment variable named in `ai.api_key_env`. If you change `api_key_env` to a different variable name, Signal will read that variable instead.

Any LLM provider supported by [LiteLLM](https://docs.litellm.ai/docs/providers) works. Set the appropriate environment variable for your provider and update `ai.default_model` accordingly.

## Changing the Default Model

Edit `.signal/config.yaml` directly:

```yaml
profile_name: blank

ai:
  default_model: openai/gpt-4o
  api_key_env: OPENAI_API_KEY
```

Then set the corresponding environment variable:

```bash
export OPENAI_API_KEY=your-key-here
```

LiteLLM model strings follow the format `provider/model-name`. See the [LiteLLM providers list](https://docs.litellm.ai/docs/providers) for the full set of supported values.
