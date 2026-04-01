# Changelog

All notable changes to this project will be documented in this file.

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
