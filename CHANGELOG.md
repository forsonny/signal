# Changelog

All notable changes to this project will be documented in this file.

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
