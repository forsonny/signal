# Project Structure

## Directory Layout

```
src/signalagent/
  __init__.py          -- package root, exports __version__
  py.typed             -- PEP 561 marker, signals type-checker support to tooling

  core/
    types.py           -- enums: AgentType, AgentStatus, TaskStatus, TaskPriority, MessageType, MemoryType
    errors.py          -- exception hierarchy: SignalError -> ConfigError, AIError, InstanceError, MemoryStoreError
    models.py          -- Pydantic models: Profile, PrimeConfig, MicroAgentConfig, Memory
    config.py          -- SignalConfig, AIConfig, load/save helpers, instance management

  ai/
    layer.py           -- AILayer wrapping LiteLLM, async completion, AIResponse model

  runtime/
    executor.py        -- Executor with error boundary, ExecutorResult, AILayerProtocol

  memory/
    storage.py         -- MemoryStorage: atomic markdown file I/O with YAML frontmatter
    index.py           -- MemoryIndex: async SQLite metadata index with tag+recency scoring
    engine.py          -- MemoryEngine: orchestrator (create, store, search, inspect, delete, rebuild)

  cli/
    app.py             -- Typer app, command registration, main() entry point
    init_cmd.py        -- `signal init` command: scaffold instance directory and config
    talk_cmd.py        -- `signal talk` command: async bridge to executor
    memory_cmd.py      -- `signal memory` command group: search and inspect subcommands

  profiles/
    blank.yaml         -- built-in blank profile (bundled with the package)

tests/
  conftest.py          -- shared fixtures (tmp dirs, mock configs, mock AI layer)

  unit/
    core/              -- tests for types, models, config (no I/O mocking needed)
    ai/                -- AI layer tests (litellm.acompletion patched with AsyncMock)
    runtime/           -- executor tests (AILayer injected via Protocol mock)
    memory/            -- memory tests: storage (tmp_path), index (in-memory SQLite), engine (both)

  integration/         -- CLI end-to-end tests using typer.testing.CliRunner
```

---

## Modules Planned but Not Yet Created

The following packages appear in Phase 3+ plans. None of their files exist yet. Do not create stubs or placeholders for them unless work on that phase has started.

| Module | Planned phase | Purpose |
|--------|---------------|---------|
| `comms/` | Phase 3 | Inter-agent message bus, message routing |
| `heartbeat/` | Phase 7 | Autonomous trigger daemon (cron, events, conditions) |
| `tools/` | Phase 4 | Agentic tool execution, sub-agent dispatch |
| `plugins/` | Phase 4 | Plugin loader, hook pipeline |
| `sessions/` | Phase 6 | Session lifecycle, interactive conversation mode |
| `conversation/` | Phase 6 | Thread management, reference resolution |
| `worktrees/` | Phase 8 | Isolated workspace creation and management |
| `forks/` | Phase 8 | Parallel approach execution, fork/merge |
| `prompt/` | Phase 5 | Token budgeting, context assembly, overflow handling |
| `safety/` | Phase 10 | Policy engine, content filtering, sandboxing |

---

## Notes on Layout Conventions

- All source code lives under `src/signalagent/`. The `src/` layout prevents accidental imports of the local directory during testing.
- Test directories mirror the source tree: `tests/unit/core/` tests `src/signalagent/core/`, and so on.
- Built-in profiles (YAML) are included as package data under `profiles/` and accessed via `importlib.resources`.
- The `py.typed` marker tells `mypy`, `pyright`, and editors that this package ships inline types.
