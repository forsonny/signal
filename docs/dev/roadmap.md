# Roadmap

## Phase Summary

| Phase | Name | Status | What it adds |
|-------|------|--------|--------------|
| 1 | Skeleton | Complete | init, talk, AI layer, config, profiles |
| 2 | Memory Foundation | Complete | Atomic files, SQLite index, tag+recency retrieval, CLI |
| 3 | Multi-Agent | Complete | Prime routing, micro-agents, message bus |
| 4a | Tool Execution + Agentic Loop | Complete | AgenticRunner, tool protocol/registry, FileSystemTool, two-tier iteration limits |
| 4b | Hooks + Sub-Agents | Complete | Hook protocol, HookRegistry, HookExecutor, LogToolCallsHook, bootstrap wiring |
| 4c | Sub-Agent Spawning | Complete | SpawnSubAgentTool, per-agent executor, ephemeral sub-agent lifecycle |
| 5 | Prompt Construction | Planned | Token budgeting, smart retrieval, overflow handling |
| 6 | Sessions + Conversation | Planned | Interactive mode, threads, reference resolution |
| 7 | Heartbeat Daemon | Planned | Autonomous triggers (cron, events, conditions) |
| 8 | Worktrees + Forks | Planned | Isolated workspaces, parallel approaches |
| 9 | Memory Advanced | Planned | Anti-corruption, consolidation, decay, embeddings |
| 10 | Safety + Docker + Full CLI | Planned | Policy engine, containerization, all commands |

---

## Dependency Graph

The phases form a directed dependency chain. Phase 1 (Skeleton) is the foundation everything else sits on. Phase 2 (Memory Foundation) must come before multi-agent work because agents need somewhere to read and write state. Phase 3 (Multi-Agent) introduces Prime routing and the message bus, which unlocks Phase 4 (Tool Execution + Hooks) and Phase 5 (Prompt Construction) -- these two can overlap since they address different concerns (execution vs. context assembly). Phase 6 (Sessions + Conversation) depends on both 3 and 5 being stable, as interactive mode needs routing and a working prompt pipeline. Phases 7 (Heartbeat) and 8 (Worktrees + Forks) are both Phase 6 dependents and can be developed in parallel. Phase 9 (Memory Advanced) builds on the basic memory from Phase 2 and requires the full agent graph from Phase 3 to be in place. Phase 10 (Safety + Docker + Full CLI) is the integration phase and depends on all prior phases being production-ready.

```
1 --> 2 --> 3 --> 4 \
               --> 5 --> 6 --> 7
                             --> 8
               --> 9 (also needs 2)
               --> 10 (needs all)
```

---

## Process

Each phase gets its own spec, implementation plan, and development cycle before work starts. No phase is begun until its dependencies are complete and reviewed. The spec defines the module contracts; the plan defines the step sequence; the cycle follows the TDD workflow described in the contributing guide.
