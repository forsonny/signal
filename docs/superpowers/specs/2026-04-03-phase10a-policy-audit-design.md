# Phase 10a: Policy Engine + Audit Trail

## Overview

Phase 10a adds declarative security policies and a structured audit trail to the Signal runtime. Profile authors define access rules in YAML (which tools an agent can use, which memories it can read). A PolicyEngine evaluates rules, a PolicyHook enforces tool access, a PolicyMemoryReader enforces memory scoping, and an AuditLogger records what happened and what was blocked.

**Depends on:** All prior phases (1-9b)

**Does not include:** Docker packaging (Phase 10b), full execution tracing, rate limiting, strict/default-deny mode.

---

## 1. Policy Rules Schema

### YAML Surface

One policy block per agent, all rules together:

```yaml
security:
  policies:
    - agent: researcher
      allow_tools: [web_search, file_system]
      allow_memory_read: [researcher, shared]
    - agent: coder
      allow_tools: [file_system, bash]
      allow_memory_read: [coder, researcher, shared]
```

### Semantics

**Allow-list only.** If an agent has `allow_tools`, it can only use those tools. If it has `allow_memory_read`, it can only see memories from those agents. Allow-lists are safer than deny-lists -- you cannot accidentally forget to deny a dangerous tool.

**Per-field opt-in.** An agent can have tool rules but no memory rules (or vice versa). Missing fields mean "no restriction on this dimension" (default-allow). Only fields that are present are enforced.

**Agents not listed.** If an agent has no entry in `policies`, everything is allowed. The audit trail logs a warning: "no policy configured for agent X." Default-allow, same as today.

**The `"shared"` keyword.** In `allow_memory_read`, the string `"shared"` refers to the shared memory pool (memories with `type=MemoryType.SHARED`), not an agent named "shared." This is a reserved keyword. All other entries in the list are agent names.

### Relationship to MicroAgentConfig.plugins

`MicroAgentConfig.plugins` controls which tool schemas are shown to an agent (soft restriction -- schema-level). `allow_tools` in the policy is hard restriction -- the PolicyHook blocks execution regardless of how the call was made. Belt and suspenders: schema filtering reduces noise, policy enforcement guarantees safety.

### Config Model

```python
class AgentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    allow_tools: list[str] | None = None
    allow_memory_read: list[str] | None = None

class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policies: list[AgentPolicy] = Field(default_factory=list)
```

`SecurityConfig` lives on the Profile: `security: SecurityConfig = Field(default_factory=SecurityConfig)`. Empty by default -- no policies, no restrictions.

---

## 2. PolicyEngine

Pure logic, no I/O, no dependencies. Lives in `security/engine.py`.

```python
class PolicyDecision(NamedTuple):
    allowed: bool
    rule: str  # which rule matched, or "no_policy" / "default_allow"

class PolicyEngine:
    def __init__(self, policies: list[AgentPolicy]) -> None:
        self._by_agent: dict[str, AgentPolicy] = {p.agent: p for p in policies}

    def check_tool_access(self, agent: str, tool_name: str) -> PolicyDecision:
        policy = self._by_agent.get(agent)
        if policy is None:
            return PolicyDecision(True, "no_policy")
        if policy.allow_tools is None:
            return PolicyDecision(True, "no_tool_rules")
        if tool_name in policy.allow_tools:
            return PolicyDecision(True, f"allow_tools:{tool_name}")
        return PolicyDecision(False, f"deny:tool:{tool_name}")

    def filter_memory_agents(self, agent: str) -> set[str] | None:
        """Return allowed agent names for memory read, or None (no restriction).
        The keyword 'shared' matches memories with type=MemoryType.SHARED."""
        policy = self._by_agent.get(agent)
        if policy is None or policy.allow_memory_read is None:
            return None
        return set(policy.allow_memory_read)

    def has_policy(self, agent: str) -> bool:
        return agent in self._by_agent
```

`PolicyDecision` carries both the verdict and the rule that produced it -- the audit trail needs the "why."

---

## 3. AuditLogger

Pure I/O, no logic. Lives in `security/audit.py`. Same pattern as LogToolCallsHook (JSONL append) and SessionManager (file-based persistence).

```python
class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: str
    event_type: str  # "tool_call" | "policy_denial" | "warning"
    agent: str
    detail: dict[str, Any]

class AuditLogger:
    def __init__(self, audit_dir: Path) -> None:
        self._audit_dir = audit_dir
        self._warned_agents: set[str] = set()

    def log(self, event: AuditEvent) -> None:
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        path = self._audit_dir / "audit.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def warn_no_policy(self, agent: str) -> None:
        """Log 'no policy configured' warning, deduplicated per agent."""
        if agent in self._warned_agents:
            return
        self._warned_agents.add(agent)
        self.log(AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="warning",
            agent=agent,
            detail={"message": f"No policy configured for agent '{agent}'"},
        ))
```

### Event Types

- **`tool_call`**: Tool executed successfully. Detail includes tool_name, duration_ms, error (if any), policy decision.
- **`policy_denial`**: Tool or memory access blocked. Detail includes what was denied and which rule blocked it.
- **`warning`**: No policy configured for an agent. Deduplicated: logged once per agent per process lifetime. In-memory `_warned_agents: set[str]`, resets per process.

Audit file lives at `{instance_dir}/logs/audit.jsonl`, alongside the existing tool call log.

---

## 4. PolicyHook

Built-in hook in `hooks/builtins/policy.py`. Implements the Hook protocol. Fail-closed.

```python
class PolicyHook:
    def __init__(self, engine: PolicyEngine, audit: AuditLogger) -> None:
        self._engine = engine
        self._audit = audit
        self._pending_start: float | None = None
        self._pending_agent: str = ""

    @property
    def name(self) -> str:
        return "policy"

    @property
    def fail_closed(self) -> bool:
        return True

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        self._pending_start = time.monotonic()
        self._pending_agent = agent

        if not self._engine.has_policy(agent):
            self._audit.warn_no_policy(agent)

        decision = self._engine.check_tool_access(agent, tool_name)
        if not decision.allowed:
            self._audit.log(AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="policy_denial",
                agent=agent,
                detail={"tool": tool_name, "rule": decision.rule},
            ))
            return ToolResult(output="", error=f"Policy denied: {tool_name}")
        return None  # allow

    async def after_tool_call(
        self, tool_name: str, arguments: dict,
        result: ToolResult, blocked: bool, agent: str = "",
    ) -> None:
        duration_ms = 0
        if self._pending_start is not None:
            duration_ms = int((time.monotonic() - self._pending_start) * 1000)
            self._pending_start = None
        self._audit.log(AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="tool_call",
            agent=self._pending_agent,
            detail={
                "tool": tool_name,
                "duration_ms": duration_ms,
                "error": result.error,
                "blocked_by_other": blocked,
            },
        ))
```

### Coexistence with LogToolCallsHook

LogToolCallsHook stays as-is. Different concerns, different failure modes, different audiences:
- LogToolCallsHook: observability, fail-open, always on. "What tools were called?"
- PolicyHook: security, fail-closed, only when policies defined. "What was allowed/denied and why?"

---

## 5. Hook Protocol + HookExecutor Changes

### Hook Protocol

`before_tool_call` and `after_tool_call` gain `agent: str = ""` parameter. Default empty string means existing hooks (LogToolCallsHook) accept the parameter without implementation changes.

```python
class Hook(Protocol):
    """Protocol for tool call hooks.

    Hooks observe and optionally block tool calls. They cannot modify
    arguments or results.

    Failure mode: hooks default to fail-open (crash = log + continue).
    Safety-critical hooks (e.g., PolicyHook) set fail_closed = True
    so a crash blocks the call rather than allowing it through.
    """

    @property
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None: ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None: ...
```

### HookExecutor Changes

1. **Constructor gains `agent: str = ""`**. Each agent gets its own HookExecutor instance at bootstrap with the agent name set.

2. **Passes `agent` to hooks.** Both `before_tool_call` and `after_tool_call` receive the agent name.

3. **Fail-closed support.** Checks `getattr(hook, 'fail_closed', False)`. If True and the hook raises, the call is blocked:

```python
for hook in hooks:
    try:
        before_result = await hook.before_tool_call(
            tool_name, arguments, agent=self._agent,
        )
    except Exception as e:
        if getattr(hook, 'fail_closed', False):
            return ToolResult(output="", error=f"Policy hook error: {e}")
        logger.warning("Hook '%s' raised (fail open): %s", hook.name, e)
        continue
```

Same pattern for `after_tool_call`:

```python
for hook in hooks:
    try:
        await hook.after_tool_call(
            tool_name, arguments, result, blocked, agent=self._agent,
        )
    except Exception as e:
        if getattr(hook, 'fail_closed', False):
            logger.error(
                "Fail-closed hook '%s' after_tool_call raised: %s",
                hook.name, e,
            )
        else:
            logger.warning("Hook '%s' after_tool_call raised: %s", hook.name, e)
```

### WorktreeProxy ISOLATED Mode

`WorktreeProxy._execute_isolated()` calls hooks directly. These calls gain the `agent` parameter (proxy already has `self._agent_name`) and the fail_closed check:

```python
# Before hooks in _execute_isolated
before_result = await hook.before_tool_call(
    tool_name, arguments, agent=self._agent_name,
)

# After hooks in _execute_isolated
await hook.after_tool_call(
    tool_name, arguments, result, blocked, agent=self._agent_name,
)
```

Both gain the same fail_closed exception handling as HookExecutor.

---

## 6. PolicyMemoryReader

Wraps MemoryEngine, implements MemoryReaderProtocol, filters results based on policy rules. Lives in `security/memory_filter.py`.

```python
class PolicyMemoryReader:
    def __init__(
        self,
        inner: MemoryReaderProtocol,
        engine: PolicyEngine,
        audit: AuditLogger,
        agent: str,
    ) -> None:
        self._inner = inner
        self._engine = engine
        self._audit = audit
        self._agent = agent

    async def search(
        self,
        tags=None, agent=None, memory_type=None,
        limit=10, touch=False, query=None,
    ) -> list[Any]:
        allowed_agents = self._engine.filter_memory_agents(self._agent)

        if allowed_agents is None:
            return await self._inner.search(
                tags=tags, agent=agent, memory_type=memory_type,
                limit=limit, touch=touch, query=query,
            )

        results = await self._inner.search(
            tags=tags, agent=agent, memory_type=memory_type,
            limit=limit, touch=touch, query=query,
        )
        filtered = []
        for memory in results:
            if memory.type.value == "shared" and "shared" in allowed_agents:
                filtered.append(memory)
            elif memory.agent in allowed_agents:
                filtered.append(memory)
            else:
                self._audit.log(AuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type="policy_denial",
                    agent=self._agent,
                    detail={
                        "denied": "memory_read",
                        "memory_id": memory.id,
                        "memory_agent": memory.agent,
                        "rule": f"allow_memory_read excludes {memory.agent}",
                    },
                ))
        return filtered
```

### Key Decisions

**Post-retrieval filtering.** Fetch all candidates, then filter. The alternative (pre-filtering by agent parameter) only handles one dimension and cannot enforce "agent X can read agent Y's memories but not agent Z's."

**Limit under-delivery.** Filtering may return fewer than `limit` results. Acceptable -- the caller asked for "up to N." Same behavior as a search with narrow tags.

**The `"shared"` keyword.** Memories with `type=MemoryType.SHARED` match `"shared"` in `allow_memory_read`. All other entries match against `memory.agent`.

---

## 7. Bootstrap Wiring

```python
async def bootstrap(instance_dir, config, profile):
    # ... existing setup (ai, bus, host, embedder, engine) ...

    # Security layer
    policy_engine = PolicyEngine(profile.security.policies)
    audit_logger = AuditLogger(instance_dir / "logs")

    # Hook registry
    hook_registry = HookRegistry()
    for hook_name in profile.hooks.active:
        hook = load_builtin_hook(hook_name, instance_dir)
        if hook is not None:
            hook_registry.register(hook)

    # PolicyHook -- conditional: only when policies exist
    if profile.security.policies:
        policy_hook = PolicyHook(engine=policy_engine, audit=audit_logger)
        hook_registry.register(policy_hook)

    # Memory reader helper
    def make_memory_reader(agent_name: str):
        if profile.security.policies:
            return PolicyMemoryReader(
                inner=engine, engine=policy_engine,
                audit=audit_logger, agent=agent_name,
            )
        return engine

    # Per-agent HookExecutor (each gets agent name)
    # Prime
    prime = PrimeAgent(
        identity=..., ai=ai, host=host, bus=bus,
        memory_reader=make_memory_reader("prime"), model=model_name,
    )

    # Micro-agents
    for micro_config in profile.micro_agents:
        agent_hook_executor = HookExecutor(
            inner=inner_executor, registry=hook_registry,
            agent=micro_config.name,
        )
        # ... worktree proxy, runner setup ...
        agent = MicroAgent(
            config=micro_config, runner=runner,
            memory_reader=make_memory_reader(micro_config.name),
            model=model_name, worktree_proxy=worktree_proxy,
        )
```

### Key Points

- **PolicyHook conditional.** Only registered when `profile.security.policies` is non-empty. No policies = no hook = zero overhead. Warnings for unconfigured agents are valuable only in mixed configurations (some agents have policies, others don't). A fully unconfigured instance has no warnings.
- **Always wrap when policies exist.** If any policy is defined, all agents get PolicyMemoryReader wrappers. The pass-through cost (one `None` check) is negligible, and unconfigured agents still get audit warnings.
- **Per-agent HookExecutor.** Each agent gets its own instance with `agent=name`. Replaces the shared executor. The `can_spawn_subs` path already creates per-agent executors -- it gains the `agent` parameter. The non-spawn path changes from shared to per-agent.
- **Blank profile unchanged.** `security` field defaults to empty SecurityConfig. No policies, no restrictions.

---

## 8. File Structure

### New Files
- `src/signalagent/security/__init__.py`
- `src/signalagent/security/engine.py` -- PolicyEngine, PolicyDecision
- `src/signalagent/security/audit.py` -- AuditLogger, AuditEvent
- `src/signalagent/security/policy_hook.py` -- PolicyHook (fail-closed, tool enforcement)
- `src/signalagent/security/memory_filter.py` -- PolicyMemoryReader (memory scoping wrapper)
- `tests/unit/security/__init__.py`
- `tests/unit/security/test_engine.py` -- PolicyEngine tests
- `tests/unit/security/test_audit.py` -- AuditLogger tests
- `tests/unit/security/test_policy_hook.py` -- PolicyHook tests
- `tests/unit/security/test_memory_filter.py` -- PolicyMemoryReader tests

### Modified Files
- `src/signalagent/core/models.py` -- AgentPolicy, SecurityConfig, Profile gains security field
- `src/signalagent/hooks/protocol.py` -- before_tool_call/after_tool_call gain `agent: str = ""`; docstring documents fail_closed
- `src/signalagent/hooks/executor.py` -- `agent` constructor param, fail_closed check, passes agent to hooks
- `src/signalagent/hooks/builtins/log_tool_calls.py` -- signature update (add `agent: str = ""` to both methods)
- `src/signalagent/worktrees/proxy.py` -- pass agent to hook calls in ISOLATED mode, add fail_closed check
- `src/signalagent/runtime/bootstrap.py` -- create security components, per-agent HookExecutor, make_memory_reader helper
- `tests/unit/core/test_models.py` -- AgentPolicy, SecurityConfig tests
- `tests/unit/hooks/test_executor.py` -- fail_closed behavior, agent passing
- `tests/unit/hooks/test_protocol.py` -- updated protocol structural subtyping
- `tests/unit/runtime/test_bootstrap.py` -- policy/audit wiring tests
- `tests/unit/worktrees/test_proxy.py` -- agent param in ISOLATED hooks, fail_closed check

---

## 9. Success Criteria

### Policy Engine
1. `PolicyEngine.check_tool_access()` returns `PolicyDecision(allowed, rule)` for allow, deny, and no-policy cases
2. `PolicyEngine.filter_memory_agents()` returns `None` (no restriction) or `set[str]` of allowed agents
3. `PolicyEngine.has_policy()` returns True/False based on agent presence in rules
4. `"shared"` keyword in `allow_memory_read` matches memories with `type=MemoryType.SHARED`, documented

### Audit Logger
5. `AuditLogger.log()` appends JSONL to `logs/audit.jsonl`
6. Three event types: `tool_call`, `policy_denial`, `warning`
7. Warning deduplication: "no policy for agent X" logged once per agent per process, not per call

### Policy Hook
8. `PolicyHook.fail_closed` returns `True`
9. `before_tool_call` blocks unauthorized tools, logs `policy_denial` event
10. `after_tool_call` logs `tool_call` event for successful executions
11. PolicyHook conditionally registered: only when `profile.security.policies` is non-empty

### Hook Protocol + Executor Changes
12. `before_tool_call` and `after_tool_call` gain `agent: str = ""` parameter
13. `HookExecutor` gains `agent: str = ""` constructor parameter, passes to hooks
14. `HookExecutor` checks `getattr(hook, 'fail_closed', False)` -- crash in fail-closed hook blocks the call
15. `LogToolCallsHook` gains `agent: str = ""` on both methods, zero behavior change

### Policy Memory Reader
16. `PolicyMemoryReader` implements `MemoryReaderProtocol`, wraps `MemoryEngine`
17. Post-retrieval filtering based on `allow_memory_read` rules
18. Filtered memories produce `policy_denial` audit events
19. `filter_memory_agents` returning `None` means pass-through (no restriction)

### Bootstrap + Config
20. `AgentPolicy` and `SecurityConfig` on Profile, `security` field defaults to empty
21. Bootstrap creates PolicyEngine, AuditLogger, PolicyHook, and per-agent PolicyMemoryReader
22. Per-agent HookExecutor with agent name replaces shared executor
23. `make_memory_reader()` helper: wrapper when policies exist, raw engine when not

### Regression
24. All existing tests pass with no modification (backward compatible)
25. `signal talk` and `signal chat` work unchanged
26. Existing profiles without `security` section work with zero restrictions

### WorktreeProxy
27. WorktreeProxy's hook calls in ISOLATED mode pass the `agent` name and respect `fail_closed`
