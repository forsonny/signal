# Quickstart

Get Signal running in under five minutes.

## Step 1: Install

Follow the [installation guide](installation.md) to clone the repo, install dependencies, and set up your API key.

## Step 2: Set Your API Key

```bash
export ANTHROPIC_API_KEY=your-key-here
```

## Step 3: Initialize an Instance

```bash
uv run signal init --profile blank
```

This creates a `.signal/` directory in your current working directory. That directory is your Signal instance -- it holds configuration, memory, session data, and logs.

## Step 4: Send a Message

```bash
uv run signal talk "hello"
```

Signal sends your message to the LLM and prints the response to stdout.

## What Just Happened

- `signal init` read the `blank` profile, created `.signal/`, and wrote `config.yaml` with default settings.
- `signal talk` located the instance by walking up the directory tree, loaded the config, built a minimal prompt using the profile's Prime identity, called the LLM via LiteLLM, and printed the response.

## Working with Memory

Signal stores memories as atomic markdown files in `.signal/memory/`. You can search and inspect them:

```bash
# Search all memories
uv run signal memory search

# Search by tags
uv run signal memory search --tags "python,preferences"

# View a specific memory
uv run signal memory inspect mem_a8f3c291
```

Memories are indexed in SQLite for fast lookup and ranked by tag relevance, recency, access frequency, and confidence. Currently, memories are created programmatically -- agent-driven memory creation comes in Phase 3.

## Next Steps

- [CLI reference](cli-reference.md) -- all available commands and options
- [Profiles](profiles.md) -- how to customize the instance identity
- [Configuration](configuration.md) -- model selection, API keys, directory layout
