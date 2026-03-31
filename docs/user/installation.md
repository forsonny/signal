# Installation

## Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- An LLM API key (Anthropic recommended; other providers work via LiteLLM)

## Install

```bash
git clone https://github.com/forsonny/signal.git
cd signal
uv sync --dev
```

`uv sync --dev` creates a virtual environment and installs all dependencies, including development tools.

## Verify

```bash
uv run signal --help
```

You should see the Signal CLI help output listing the available commands.

## API Key Setup

Signal uses [LiteLLM](https://docs.litellm.ai/) under the hood, which supports any major LLM provider. Set the environment variable for your provider before running any command that calls the LLM.

**Anthropic (default):**

```bash
export ANTHROPIC_API_KEY=your-key-here
```

**Other providers** supported by LiteLLM work the same way -- set the appropriate environment variable (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`) and change the `ai.default_model` in your instance config to match. See [Configuration](configuration.md) for details.

To persist the key across sessions, add the export to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.).
