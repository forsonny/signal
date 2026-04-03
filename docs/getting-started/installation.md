# Installation

**What you'll learn:**

- System prerequisites for running Signal
- How to clone the repository and install dependencies
- How to verify your installation works
- How to configure API keys for LLM providers
- How to persist your API key across shell sessions

---

## Prerequisites

Signal requires:

| Requirement | Minimum version |
|-------------|----------------|
| Python      | 3.11+          |
| uv          | 0.1+           |
| Git         | any recent     |

**Python 3.11+** -- Signal uses modern Python features including `str | None` union syntax and `asyncio` improvements from 3.11. Check your version:

```bash
python --version
```

**uv** -- Signal uses [uv](https://docs.astral.sh/uv/) for dependency management. Install it if you haven't:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**An LLM API key** -- Signal uses [LiteLLM](https://docs.litellm.ai/) under the hood, so it works with any supported provider. The default model is `anthropic/claude-sonnet-4-20250514`, which requires an Anthropic API key.

---

## Clone and install

```bash
git clone https://github.com/forsonny/signal.git
cd signal
uv sync --dev
```

`uv sync --dev` installs the `signalagent` package in editable mode along with all development and documentation dependencies, including pytest, pytest-asyncio, and mkdocs-material.

---

## Verify installation

Run the CLI to confirm everything is wired up:

```bash
uv run signal --help
```

You should see output listing Signal's available commands: `init`, `talk`, `chat`, `fork`, `memory`, `sessions`, and `worktree`.

---

## API key setup

Signal reads the API key from an environment variable at runtime. The variable name is configured in `.signal/config.yaml` (default: `ANTHROPIC_API_KEY`).

### Anthropic (default)

Set the key for your current shell session:

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Windows (cmd)
set ANTHROPIC_API_KEY=sk-ant-...
```

### Other LiteLLM providers

Signal delegates all LLM calls to LiteLLM, so any provider LiteLLM supports works. Change the model and API key variable in `.signal/config.yaml` after running `signal init`:

```yaml
ai:
  default_model: "openai/gpt-4o"
  api_key_env: "OPENAI_API_KEY"
```

Or for a local model via Ollama:

```yaml
ai:
  default_model: "ollama/llama3"
  api_key_env: "OLLAMA_API_KEY"
```

Set the corresponding environment variable for whichever provider you choose.

---

## Persisting your API key

To avoid setting the environment variable every time you open a terminal, add it to your shell profile.

### Bash (~/.bashrc or ~/.bash_profile)

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

### Zsh (~/.zshrc)

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc
```

### Fish (~/.config/fish/config.fish)

```bash
set -Ux ANTHROPIC_API_KEY "sk-ant-..."
```

### Windows (PowerShell profile)

```powershell
# Add to your PowerShell profile
Add-Content $PROFILE 'New-Variable -Name "ANTHROPIC_API_KEY" -Value "sk-ant-..." -Scope Global -ErrorAction SilentlyContinue; $env:ANTHROPIC_API_KEY = "sk-ant-..."'
```

### Windows (system-wide)

```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

---

## Next steps

- [Quickstart](quickstart.md) -- send your first message to Signal
- [Your First Profile](first-profile.md) -- customize Signal with micro-agents
- [Configuration](../user-guide/configuration.md) -- full config.yaml reference
