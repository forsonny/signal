# Changelog

All notable changes to this project will be documented in this file.

## [0.13.0] - 2026-04-03

### Added
- EmbeddingProtocol in core/protocols.py for dependency-injected embedding
- LiteLLMEmbedding wrapping litellm.aembedding() with attribute/dict response handling
- cosine_similarity pure function for vector comparison
- Shared scoring module (memory/scoring.py) -- single source of truth for scoring formula
- memory_embeddings SQLite table with struct-packed BLOB storage
- MemoryIndex.store_embedding(), get_embedding(), get_all_embeddings()
- Two-phase semantic search: embedding candidates -> existing scoring formula
- Relevance slot: tag_score when tags provided, embedding_similarity when query-only
- MemoryEngine.rebuild_embeddings() with batch backfill
- embedding_model on MemoryConfig (presence is feature flag)
- Bootstrap creates LiteLLMEmbedding and injects when embedding_model is set

### Changed
- MemoryEngine.search() gains query: str | None parameter for semantic search
- MemoryReaderProtocol.search() gains query: str | None parameter (backward compatible)
- MemoryEngine constructor accepts embedder parameter
- MemoryEngine.store() embeds content when embedder present (file-first ordering)
- MemoryIndex.search() uses shared scoring module (no formula duplication)

## [0.12.0] - 2026-04-02

### Added
- Decay multiplier: time-based scoring with configurable half-life (replaces additive recency)
- MemoryConfig on Profile with decay_half_life_days setting
- MemoryKeeperConfig for optional maintenance agent scheduling
- MemoryKeeperAgent(BaseAgent): purpose-built agent for memory maintenance
- MemoryEngine.archive() with changelog entry and index flag
- MemoryEngine.consolidate() with source supersession and archival
- MemoryEngine.find_groups() for tag-based candidate grouping (O(n^2) per agent)
- MemoryEngine.find_stale() for decay-based stale detection
- MemoryIndex.archive() dedicated single-column update
- MemoryIndex.list_active() for maintenance queries
- Memory maintenance prompts module with defensive JSON parsing
- Bootstrap wires MemoryKeeperAgent with ClockTrigger when config present

### Changed
- MemoryIndex.search() scoring: tag(0.5) + frequency(0.25) + confidence(0.25) * decay_factor (was: tag(0.4) + recency(0.3) + frequency(0.2) + confidence(0.1))
- AgentHost.list_micro_agents() includes MEMORY_KEEPER type for Prime routing
- MemoryEngine constructor accepts decay_half_life_days parameter
- Blank profile includes memory section with decay_half_life_days: 30

## [0.11.0] - 2026-04-02

### Added
- ForkRunner: semaphore-bounded parallel task execution with asyncio.gather
- ForkResult model for fork branch results
- ForkConfig with max_concurrent_branches (default 2) on Profile
- WORKTREE_MERGE_PATTERN shared constant for worktree ID extraction
- `signal fork "task A" "task B"` CLI command for parallel approaches
- `--concurrency` flag to override max_concurrent_branches per invocation

### Changed
- WorktreeProxy gains asyncio.Lock and task_lock() for fork branch serialization
- WorktreeProxyProtocol gains task_lock() method
- MicroAgent._handle() acquires task_lock() around full task lifecycle
- MicroAgent._handle() refactored to _handle/_handle_inner for lock wrapping

## [0.10.0] - 2026-04-02

### Added
- WorktreeManager: git worktree creation (git worktree add) and directory copy fallback
- WorktreeProxy: per-agent tool executor wrapper with lazy worktree creation on first write
- WorktreeManifest: JSONL persistence for worktree lifecycle tracking
- WorktreeResult and WorktreeRecord Pydantic models
- WorktreeProxyProtocol in core/protocols for dependency injection
- `signal worktree list` command showing pending worktrees
- `signal worktree merge <id>` command copying changed files to workspace
- `signal worktree discard <id>` command removing worktree without merging
- Shared IGNORE_DIRS constant in core/constants (used by FileChangeDetector and WorktreeManager)

### Changed
- MicroAgent accepts optional WorktreeProxyProtocol, appends review instructions after file writes
- MicroAgent preserves worktree state on runner failure (partial changes reviewable)
- Bootstrap wraps each micro-agent's tool executor with WorktreeProxy (outermost layer)
- FileChangeDetector imports IGNORE_DIRS from shared constant instead of local definition

## [0.9.0] - 2026-04-02

### Added
- HeartbeatScheduler: in-process async trigger loop with 1-second tick interval
- ClockTrigger model with 5-field cron expression matching (ISO day-of-week)
- FileEventTrigger model with git-status polling and mtime fallback
- TriggerGuards: cooldown, max_fires, and consecutive error threshold
- FileChangeDetector: git status --porcelain diffing with silent baseline reset
- Pure-function cron matcher and validator (heartbeat/cron.py)
- HEARTBEAT_SENDER virtual sender constant
- Cron validation at bootstrap (fail-fast on invalid expressions)

### Changed
- HeartbeatConfig uses typed trigger models (ClockTrigger, FileEventTrigger) instead of list[dict]
- HeartbeatConfig.condition_triggers removed (deferred -- agents evaluate predicates on clock ticks)
- MessageBus uses _VIRTUAL_SENDERS set instead of chained sender checks
- Bootstrap creates and starts HeartbeatScheduler as background asyncio task when triggers are defined

## [0.8.0] - 2026-04-02

### Added
- SessionManager for JSONL-based conversation persistence (create, load, append, list)
- Turn and SessionSummary models for session data
- Message.history field for explicit conversation history transport
- Conversation history injection in AgenticRunner and PrimeAgent
- `signal chat` interactive REPL with session create/resume
- `signal sessions list` command for browsing recent sessions
- Session ID printed on start and exit for resumability

### Changed
- RunnerProtocol gains optional history parameter
- PrimeAgent._handle_directly() accepts conversation history
- Executor gains optional session_id for multi-turn persistence
- Bootstrap injects SessionManager into Executor

## [0.7.0] - 2026-04-01

### Added
- Token counting utilities (prompts/tokens.py) wrapping LiteLLM for model-aware token budgeting
- Pure-function prompt builder (prompts/builder.py) assembling token-budgeted system prompts from identity + memories
- MemoryReaderProtocol in core/protocols.py for dependency-inverted memory access
- Memory injection in MicroAgent and PrimeAgent via MemoryReaderProtocol
- DEFAULT_MEMORY_LIMIT constant for caller-side retrieval control

### Changed
- MicroAgent._build_system_prompt() renamed to _build_identity() (static identity only)
- PrimeAgent._handle_directly() enriches prompt with retrieved memories
- PrimeAgent._route() explicitly excludes memory injection (classification, not knowledge)
- Bootstrap injects MemoryEngine and model name into all agents

## [0.6.0] - 2026-03-31

### Added
- SpawnSubAgentTool for ephemeral sub-agent delegation via tool calls
- Per-agent executor pipeline for micro-agents with can_spawn_subs
- Sub-agents inherit parent's tools minus spawn (no recursion)

### Changed
- Bootstrap creates per-agent executors for spawning agents

## [0.5.0] - 2026-03-31

### Added
- Hook protocol with before_tool_call (block/allow) and after_tool_call (observe)
- HookRegistry for instance-wide hook management
- HookExecutor wrapping ToolExecutor with before/after hook lifecycle
- LogToolCallsHook: JSONL logging of all tool calls with timing and blocked status
- HooksConfig model with active hook list on Profile

### Changed
- Bootstrap wires hook pipeline: inner executor -> HookExecutor

## [0.4.0] - 2026-03-31

### Added
- AgenticRunner with tool-calling agentic loop
- Tool protocol, ToolRegistry with LiteLLM-format schema generation
- FileSystemTool (read/write/list, scoped to workspace, size-capped reads)
- ToolCallRequest, ToolResult, ToolConfig models
- RunnerProtocol, ToolExecutor, AILayerProtocol in core/protocols
- Two-tier iteration limits (global + per-agent)

### Changed
- AILayer.complete() accepts optional tools parameter
- AIResponse includes tool_calls field
- MicroAgent delegates to RunnerProtocol (no direct AI reference)
- Bootstrap wires tool pipeline (registry, executor, runners)

## [0.3.0] - 2026-03-31

### Added
- PrimeAgent with LLM-based routing to micro-agents and direct handling fallback
- MicroAgent with skill-based system prompt template
- In-process MessageBus with typed message delivery and talks_to permission enforcement
- AgentHost registry for agent lifecycle management
- BaseAgent with template method for automatic BUSY/IDLE status transitions
- Bootstrap wiring function for single-point runtime setup
- Message model with auto-filled id/created, parent_id threading, and metadata bag
- RoutingError for routing failures (talks_to violations, unknown agents)
- PRIME_AGENT and USER_SENDER constants in core/types

### Changed
- Executor refactored to delegate to MessageBus instead of calling AILayer directly
- `signal talk` now routes through the multi-agent bus

## [0.2.0] - 2026-03-31

### Added
- MemoryStorage: atomic markdown file I/O with YAML frontmatter
- MemoryIndex: async SQLite metadata index with tag+recency scored search
- MemoryEngine: orchestrator tying storage and index together
- `signal memory search` command with tag filtering and Rich table output
- `signal memory inspect` command for full metadata display
- Memory model with confidence validation, versioning, and changelog
- MemoryType enum (identity, learning, pattern, outcome, context, shared)
- MemoryStoreError for storage/index failures
- Path routing: shared/, prime/{type}/, micro/{agent}/{type}/

## [0.1.0] - 2026-03-31

### Added
- Typer CLI with `signal init` and `signal talk` commands
- AILayer wrapping LiteLLM for async completion
- Executor with error boundary (exceptions never propagate)
- Profile system with YAML manifests and built-in blank profile
- SignalConfig with YAML persistence and instance directory management
- Core types: AgentType, AgentStatus, TaskStatus, TaskPriority, MessageType
- Pydantic models with extra="forbid" for all data boundaries
- AILayerProtocol for dependency injection in tests
