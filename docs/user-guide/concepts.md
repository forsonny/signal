# Core Concepts

**What you'll learn:**

- Signal's agent architecture (Prime and micro-agents)
- How memory works (types, scoring, semantic search)
- How agents communicate via the message bus
- How heartbeat triggers drive autonomous behavior
- How tools, hooks, sessions, worktrees, and security fit together

---

## Prime Agent

The Prime agent is the entry point for all user interaction. Every message you send via `signal talk` or `signal chat` goes to Prime first. Prime has a configurable system-prompt identity defined in the profile's `prime.identity` field. It can delegate work to micro-agents, use tools, and read/write memories. There is exactly one Prime agent per Signal instance.

## Micro-Agents

Micro-agents are specialist agents registered from the profile's `micro_agents` list. Each micro-agent has a name, a skill description, an allowed set of tools (via `plugins`), and routing permissions (via `talks_to`). Prime delegates to micro-agents when a task matches their skill. Micro-agents can also talk to other micro-agents if their `talks_to` list permits it. Each micro-agent runs its own agentic loop with a configurable iteration cap (`max_iterations`).

## Memory

Signal agents build persistent knowledge stored as markdown files with YAML frontmatter, indexed in SQLite for fast retrieval. Each memory has a type (identity, learning, pattern, outcome, context, or shared), a confidence score (0.0 to 1.0), tags for filtering, and version tracking with changelog entries. Memory relevance decays over time based on a configurable half-life (`decay_half_life_days`). When an embedding model is configured, semantic search is available alongside tag and type filtering. The MemoryKeeper agent, when enabled, runs on a cron schedule to archive stale memories and consolidate duplicates.

## Message Bus

Agents communicate through a typed message bus. Messages carry a type (task, result, request, response, escalation, spawn, report, trigger, or memory_write), a sender, a recipient, and a content payload. The `talks_to` field on each micro-agent defines which agents it is allowed to message. Prime can message any agent. The bus enforces routing permissions and attaches metadata (timestamps, message IDs, parent IDs) automatically.

## Heartbeat

The heartbeat system drives autonomous agent behavior without user input. Clock triggers fire when the current time matches a 5-field cron expression, sending a message to a named agent. File event triggers poll a directory for changes at a configurable interval and fire when files are added, modified, or deleted. Both trigger types support safety guards: cooldown periods, maximum fire counts, and error thresholds that auto-disable misbehaving triggers.

## Tools and Hooks

Tools are capabilities that agents can invoke during their agentic loop -- file system operations, shell commands, web searches, MCP servers, and custom scripts. Tools are registered by name in the profile's `plugins.available` list and granted to individual agents via their `plugins` field. Hooks intercept every tool call across the instance, running before and/or after execution. Hooks enable audit logging, policy enforcement, rate limiting, and other cross-cutting concerns. Active hooks are listed in the profile's `hooks.active` field.

## Sessions

A session is a multi-turn conversation between the user and Prime. Sessions are created automatically by `signal chat` and stored in `.signal/data/sessions/`. Each session tracks turns (user and assistant messages) with timestamps. Sessions can be resumed by ID, listed to see recent conversations, and their history can be replayed. Sessions are independent -- starting a new chat creates a new session with no carry-over from previous ones.

## Worktrees and Forks

Forks let an agent explore multiple approaches to a problem in parallel. The `signal fork` command takes two or more task descriptions and runs each in a separate worktree -- an isolated copy of the workspace. Each branch executes independently with its own agent pipeline. When all branches complete, you review the results and choose which to merge into the main workspace with `signal worktree merge` or discard with `signal worktree discard`. The `fork.max_concurrent_branches` profile setting controls how many branches run simultaneously.

## Security

Signal's security model uses declarative, per-agent allow-list policies defined in the profile's `security.policies` list. Each policy names an agent and optionally restricts which tools it can call (`allow_tools`) and which memory scopes it can read (`allow_memory_read`). When a field is `null`, the agent has unrestricted access; when it's an empty list, the agent has no access. Policies are evaluated at tool-call time by the PolicyEngine and at memory-search time by the PolicyMemoryReader.

---

## Next steps

- [CLI Reference](cli-reference.md) -- every command with syntax and examples
- [Configuration](configuration.md) -- config.yaml format and all fields
- [Profiles](profiles.md) -- complete profile YAML schema
