# Roadmap

## Phase History

| Phase | Name | What It Added |
|-------|------|---------------|
| 1 | Skeleton | `init`, `talk`, AI layer, config system, YAML profiles |
| 2 | Memory Foundation | Atomic file store, SQLite index, tag + recency retrieval |
| 3 | Multi-Agent | Prime routing, micro-agents, message bus |
| 4a | Tool Execution | AgenticRunner, tool protocol/registry, FileSystemTool |
| 4b | Hooks | Hook protocol, registry, executor, LogToolCallsHook |
| 4c | Sub-Agent Spawning | SpawnSubAgentTool, per-agent executor |
| 5 | Prompt Construction | Token budgeting, context assembly, memory injection |
| 6 | Sessions | JSONL persistence, interactive REPL (`chat`) |
| 7 | Heartbeat Daemon | Async scheduler, clock and event triggers |
| 8a | Worktrees | Isolated workspaces via git worktrees |
| 8b | Forks | Parallel execution, semaphore-based concurrency |
| 9a | Memory Lifecycle | Decay, consolidation, MemoryKeeper agent |
| 9b | Memory Embeddings | Semantic search, vector store |
| 10a | Policy + Audit | Declarative policies, audit trail, fail-closed hooks |
| 10b | Docker Packaging | Multi-stage Dockerfile, auto-init entrypoint |

## Current Status

All phases complete. Current release: **v0.15.0**.

## Future Direction

Signal's core is stable and extensible by design -- new agents, tools, hooks, and profiles can be added without modifying internals. Areas under consideration:

- **Plugin ecosystem** -- a discovery and distribution mechanism for community-built agents and tools
- **Built-in tool library** -- more tools out of the box (HTTP, database, shell, code analysis)
- **Profile gallery** -- curated profiles for common workflows (devtools, research, ops)
- **Deployment options** -- Kubernetes manifests, cloud-native packaging, managed hosting patterns
- **Multi-model routing** -- per-agent model selection and fallback chains

Contributions welcome. See [Contributing](developer-guide/contributing.md).
