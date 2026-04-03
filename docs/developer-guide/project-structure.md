# Project Structure

## What you'll learn

- The complete source tree under `src/signalagent/` with module descriptions
- The test directory layout and how it mirrors the source tree
- Layout conventions used throughout the codebase

---

## Source tree

```
src/signalagent/
    __init__.py               -- Package root, version string
    py.typed                  -- PEP 561 marker for type checker support

    core/
        __init__.py
        config.py             -- SignalConfig, AIConfig, load_config, load_profile, create_instance, find_instance
        constants.py          -- IGNORE_DIRS and other shared constants
        errors.py             -- SignalError exception hierarchy (ConfigError, AIError, etc.)
        models.py             -- All cross-boundary Pydantic models: Profile, Message, Memory, ToolResult, Turn, etc.
        protocols.py          -- @runtime_checkable protocols for DI: AILayerProtocol, RunnerProtocol, ToolExecutor, etc.
        types.py              -- Enums: AgentType, AgentStatus, TaskStatus, MessageType, MemoryType; well-known names

    agents/
        __init__.py
        base.py               -- BaseAgent: template method pattern, status lifecycle (BUSY/IDLE)
        host.py               -- AgentHost: registry backed by MessageBus, registration and lookup
        micro.py              -- MicroAgent: skill-based specialist, delegates to RunnerProtocol
        prime.py              -- PrimeAgent: LLM routing to micro-agents or direct handling fallback

    ai/
        __init__.py
        layer.py              -- AILayer: wraps LiteLLM acompletion, returns AIResponse; tool call parsing
        embedding.py          -- LiteLLMEmbedding: wraps LiteLLM aembedding for vector generation

    runtime/
        __init__.py
        bootstrap.py          -- bootstrap(): single wiring point for the full multi-agent runtime
        executor.py           -- Executor: sends user messages to Prime via bus, error boundary, session persistence
        runner.py             -- AgenticRunner: agentic loop (LLM -> tool call -> result -> repeat)

    comms/
        __init__.py
        bus.py                -- MessageBus: typed message delivery, talks_to enforcement, message log

    tools/
        __init__.py
        protocol.py           -- Tool protocol: name, description, parameters, execute
        registry.py           -- ToolRegistry: lookup by name, LiteLLM-format schema generation
        builtins/
            __init__.py       -- load_builtin_tool(): deferred import factory
            file_system.py    -- FileSystemTool: scoped read/write/list within instance directory
            spawn_sub_agent.py -- SpawnSubAgentTool: spawns ephemeral sub-agents for task delegation

    hooks/
        __init__.py
        protocol.py           -- Hook protocol: before_tool_call, after_tool_call
        registry.py           -- HookRegistry: ordered storage, registration-order iteration
        executor.py           -- HookExecutor: wraps ToolExecutor with before/after hook lifecycle
        builtins/
            __init__.py       -- load_builtin_hook(): deferred import factory
            log_tool_calls.py -- LogToolCallsHook: JSONL logging of every tool call with timing

    memory/
        __init__.py
        engine.py             -- MemoryEngine: public API orchestrating storage, index, and embeddings
        storage.py            -- MemoryStorage: markdown files with YAML frontmatter on disk
        index.py              -- MemoryIndex: aiosqlite-backed search and metadata index
        scoring.py            -- Shared scoring formula: relevance, frequency, confidence, decay
        similarity.py         -- cosine_similarity(): vector comparison for semantic search
        keeper.py             -- MemoryKeeperAgent: scheduled maintenance (consolidation, archival)
        prompts.py            -- LLM prompt templates for memory classification and consolidation

    prompts/
        __init__.py
        builder.py            -- build_system_prompt(): token-budgeted system prompt assembly
        tokens.py             -- count_tokens(), get_context_window(): LiteLLM token utilities

    security/
        __init__.py
        engine.py             -- PolicyEngine: pure rules evaluation (tool access, memory scoping)
        audit.py              -- AuditLogger: JSONL audit trail for policy decisions
        policy_hook.py        -- PolicyHook: fail-closed tool access enforcement hook
        memory_filter.py      -- PolicyMemoryReader: post-retrieval memory filtering by policy scope

    sessions/
        __init__.py
        manager.py            -- SessionManager: JSONL-based conversation session persistence

    heartbeat/
        __init__.py
        cron.py               -- Cron expression parsing: validate_cron(), cron_match()
        detector.py           -- FileChangeDetector: polling-based file modification detection
        models.py             -- ClockTrigger, FileEventTrigger, TriggerGuards, TriggerState
        scheduler.py          -- HeartbeatScheduler: async tick loop for clock and file triggers

    worktrees/
        __init__.py
        manager.py            -- WorktreeManager: git worktree / directory copy mechanics
        manifest.py           -- WorktreeManifest: append-only record of worktree operations
        models.py             -- WorktreeRecord, WorktreeResult, ForkResult, WORKTREE_MERGE_PATTERN
        proxy.py              -- WorktreeProxy: per-agent PASSTHROUGH/ISOLATED state machine
        fork.py               -- ForkRunner: semaphore-bounded parallel branch execution

    cli/
        __init__.py
        app.py                -- Typer app: main entry point, subcommand registration
        init_cmd.py           -- signal init: create a new instance
        talk_cmd.py           -- signal talk: single-shot message
        chat_cmd.py           -- signal chat: interactive REPL with session persistence
        memory_cmd.py         -- signal memory: search, inspect, store, delete, rebuild
        sessions_cmd.py       -- signal sessions: list, resume, delete
        worktree_cmd.py       -- signal worktree: list, merge, discard, diff
        fork_cmd.py           -- signal fork: parallel branch execution

    profiles/
        (YAML files)          -- Built-in profile templates loaded by load_profile()
```

---

## Test tree

Tests mirror the source layout. Unit tests live under `tests/unit/` with
the same package structure. Integration tests live under `tests/integration/`.

```
tests/
    __init__.py
    conftest.py                          -- Shared fixtures: mock_ai_response

    unit/
        __init__.py
        core/
            test_config.py               -- Config loading, profile resolution, instance creation
            test_constants.py            -- IGNORE_DIRS contents
            test_models.py               -- Pydantic model validation: Profile, Message, Memory, etc.
            test_protocols.py            -- Protocol runtime-checkability
            test_types.py                -- Enum value checks
        agents/
            test_base.py                 -- BaseAgent status transitions, template method
            test_host.py                 -- AgentHost registration, lookup, micro-agent listing
            test_micro.py                -- MicroAgent routing, memory injection, worktree handling
            test_prime.py                -- PrimeAgent routing, direct handling, fallback
        ai/
            test_layer.py                -- AILayer completion, tool call parsing
            test_embedding.py            -- LiteLLMEmbedding vector generation
        runtime/
            test_bootstrap.py            -- Full bootstrap wiring validation
            test_executor.py             -- Executor error boundary, session persistence
            test_runner.py               -- AgenticRunner loop, iteration limits, error handling
        comms/
            test_bus.py                  -- MessageBus delivery, talks_to enforcement, virtual senders
        tools/
            builtins/
                test_file_system.py      -- FileSystemTool read/write/list, path traversal rejection
                test_spawn_sub_agent.py  -- SpawnSubAgentTool delegation, naming
            test_registry.py             -- ToolRegistry registration, schema generation
        hooks/
            builtins/
                test_log_tool_calls.py   -- LogToolCallsHook JSONL output, timing
            test_executor.py             -- HookExecutor lifecycle, blocking, fail-open/fail-closed
            test_registry.py             -- HookRegistry ordering
        memory/
            test_engine.py               -- MemoryEngine CRUD, search
            test_storage.py              -- MemoryStorage file read/write
            test_index.py                -- MemoryIndex SQLite operations
            test_scoring.py              -- Scoring formula edge cases
            test_similarity.py           -- Cosine similarity computation
            test_archive.py              -- Archive lifecycle, changelog
            test_consolidate.py          -- Consolidation flow, superseded_by
            test_find_groups.py          -- Union-find grouping by tag overlap
            test_semantic_search.py      -- Two-phase semantic retrieval
            test_embedding_storage.py    -- Embedding store/retrieve round-trip
            test_keeper.py               -- MemoryKeeperAgent maintenance pass
            test_prompts.py              -- Classification and consolidation prompt templates
        prompts/
            test_builder.py              -- Token budgeting, memory formatting
            test_tokens.py               -- Token counting, context window lookup
        security/
            test_engine.py               -- PolicyEngine tool access, memory scoping
            test_audit.py                -- AuditLogger JSONL output
            test_policy_hook.py          -- PolicyHook blocking, audit trail
            test_memory_filter.py        -- PolicyMemoryReader filtering
        sessions/
            test_manager.py              -- SessionManager create/append/load/list
        heartbeat/
            test_cron.py                 -- Cron parsing and matching
            test_detector.py             -- FileChangeDetector polling
            test_models.py               -- Trigger model validation
            test_scheduler.py            -- HeartbeatScheduler tick loop, guards, dispatch
        worktrees/
            test_manager.py              -- WorktreeManager create/diff/merge/cleanup
            test_manifest.py             -- WorktreeManifest append/get/list
            test_models.py               -- WorktreeRecord, ForkResult validation
            test_proxy.py                -- WorktreeProxy state machine, isolation
            test_fork.py                 -- ForkRunner concurrency, result extraction

    integration/
        test_cli.py                      -- CLI commands via Typer CliRunner
        test_memory_cli.py               -- Memory CLI subcommands end-to-end
```

---

## Layout conventions

### One concern per file

Each module addresses a single concern. Models live in `core/models.py`,
not scattered across packages. Protocols live in `core/protocols.py`.
Errors live in `core/errors.py`.

### Deferred imports for optional loading

Built-in tools and hooks use deferred imports in their `__init__.py`
factory functions (`load_builtin_tool`, `load_builtin_hook`). This keeps
the import graph clean -- unused tools are never imported.

### Test naming

Test files mirror the source file they cover: `src/signalagent/agents/prime.py`
is tested in `tests/unit/agents/test_prime.py`. Test classes are named
after the behavior being verified (e.g., `TestRunnerWithTools`,
`TestRunnerIterationLimit`).

### Package `__init__.py` files

All `__init__.py` files are present (required for Python package discovery)
but intentionally kept minimal. Public re-exports are avoided to keep the
import graph explicit.

---

## Next steps

- [Architecture](architecture.md) -- how the modules connect and interact
- [Contributing](contributing.md) -- development setup and workflow
- [Testing](testing.md) -- test patterns and fixtures
