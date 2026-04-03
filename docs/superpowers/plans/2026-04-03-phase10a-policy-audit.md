# Phase 10a: Policy Engine + Audit Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add declarative security policies and a structured audit trail so agents can only use authorized tools and see authorized memories, with every decision recorded.

**Architecture:** Four components with clear responsibilities: PolicyEngine (pure rules logic), AuditLogger (JSONL writer), PolicyHook (tool enforcement via existing hook pipeline), PolicyMemoryReader (memory scoping wrapper). All wired at bootstrap via dependency injection.

**Tech Stack:** Python, Pydantic, pytest, existing Signal hook/protocol infrastructure.

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/signalagent/security/__init__.py` | Package init |
| `src/signalagent/security/engine.py` | PolicyEngine + PolicyDecision -- pure rules evaluation |
| `src/signalagent/security/audit.py` | AuditLogger + AuditEvent -- JSONL append |
| `src/signalagent/security/policy_hook.py` | PolicyHook -- fail-closed tool enforcement |
| `src/signalagent/security/memory_filter.py` | PolicyMemoryReader -- memory scoping wrapper |
| `tests/unit/security/__init__.py` | Test package init |
| `tests/unit/security/test_engine.py` | PolicyEngine tests |
| `tests/unit/security/test_audit.py` | AuditLogger tests |
| `tests/unit/security/test_policy_hook.py` | PolicyHook tests |
| `tests/unit/security/test_memory_filter.py` | PolicyMemoryReader tests |

### Modified Files
| File | Change |
|------|--------|
| `src/signalagent/core/models.py` | Add AgentPolicy, SecurityConfig; Profile gains `security` field |
| `src/signalagent/hooks/protocol.py` | Add `agent: str = ""` to both methods; document fail_closed in docstring |
| `src/signalagent/hooks/executor.py` | Add `agent` constructor param; fail_closed check; pass agent to hooks |
| `src/signalagent/hooks/builtins/log_tool_calls.py` | Add `agent: str = ""` to both method signatures |
| `src/signalagent/worktrees/proxy.py` | Pass agent to hook calls in ISOLATED mode; add fail_closed check |
| `src/signalagent/runtime/bootstrap.py` | Create security components; per-agent HookExecutor; make_memory_reader |
| `tests/unit/core/test_models.py` | AgentPolicy, SecurityConfig tests |
| `tests/unit/hooks/test_executor.py` | fail_closed behavior; agent passing |
| `tests/unit/runtime/test_bootstrap.py` | Policy/audit wiring tests |
| `tests/unit/worktrees/test_proxy.py` | Agent param in ISOLATED hooks; fail_closed check |

---

### Task 1: Config Models (AgentPolicy + SecurityConfig)

**Files:**
- Modify: `src/signalagent/core/models.py:65-98`
- Test: `tests/unit/core/test_models.py`

- [ ] **Step 1: Write failing tests for AgentPolicy and SecurityConfig**

Add to the bottom of `tests/unit/core/test_models.py`:

```python
from signalagent.core.models import AgentPolicy, SecurityConfig


class TestAgentPolicy:
    def test_minimal(self):
        policy = AgentPolicy(agent="researcher")
        assert policy.agent == "researcher"
        assert policy.allow_tools is None
        assert policy.allow_memory_read is None

    def test_with_tool_rules(self):
        policy = AgentPolicy(agent="researcher", allow_tools=["web_search", "file_system"])
        assert policy.allow_tools == ["web_search", "file_system"]

    def test_with_memory_rules(self):
        policy = AgentPolicy(agent="researcher", allow_memory_read=["researcher", "shared"])
        assert policy.allow_memory_read == ["researcher", "shared"]

    def test_full(self):
        policy = AgentPolicy(
            agent="researcher",
            allow_tools=["web_search"],
            allow_memory_read=["researcher", "shared"],
        )
        assert policy.agent == "researcher"
        assert policy.allow_tools == ["web_search"]
        assert policy.allow_memory_read == ["researcher", "shared"]

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            AgentPolicy(agent="researcher", bogus="bad")


class TestSecurityConfig:
    def test_defaults_empty(self):
        cfg = SecurityConfig()
        assert cfg.policies == []

    def test_with_policies(self):
        cfg = SecurityConfig(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search"]),
            AgentPolicy(agent="coder", allow_tools=["file_system", "bash"]),
        ])
        assert len(cfg.policies) == 2
        assert cfg.policies[0].agent == "researcher"

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            SecurityConfig(policies=[], bogus="bad")


class TestProfileSecurityConfig:
    def test_profile_has_security_default(self):
        p = Profile(name="test")
        assert isinstance(p.security, SecurityConfig)
        assert p.security.policies == []

    def test_profile_with_security(self):
        p = Profile(
            name="test",
            security=SecurityConfig(policies=[
                AgentPolicy(agent="researcher", allow_tools=["web_search"]),
            ]),
        )
        assert len(p.security.policies) == 1
```

Also add `AgentPolicy, SecurityConfig` to the import block at the top of the file (line 8):

```python
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HeartbeatConfig,
    HooksConfig,
    ForkConfig,
    MemoryConfig,
    MemoryKeeperConfig,
    Memory,
    Message,
    ToolCallRequest,
    ToolResult,
    ToolConfig,
    Turn,
    SessionSummary,
    AgentPolicy,
    SecurityConfig,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/core/test_models.py::TestAgentPolicy -v`
Expected: FAIL with `ImportError: cannot import name 'AgentPolicy'`

- [ ] **Step 3: Implement AgentPolicy, SecurityConfig, and add security to Profile**

In `src/signalagent/core/models.py`, add after the `MemoryKeeperConfig` class (after line 81):

```python
class AgentPolicy(BaseModel):
    """Policy rules for a single agent -- tool access and memory scoping."""
    model_config = ConfigDict(extra="forbid")

    agent: str
    allow_tools: list[str] | None = None
    allow_memory_read: list[str] | None = None


class SecurityConfig(BaseModel):
    """Declarative security policies -- allow-list rules per agent."""
    model_config = ConfigDict(extra="forbid")

    policies: list[AgentPolicy] = Field(default_factory=list)
```

Add the `security` field to the `Profile` class (after the `memory_keeper` field):

```python
    security: SecurityConfig = Field(default_factory=SecurityConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/core/test_models.py -v`
Expected: All tests PASS including the new ones

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/core/models.py tests/unit/core/test_models.py
git commit -m "feat(core): add AgentPolicy and SecurityConfig models"
```

---

### Task 2: PolicyEngine (Pure Rules Evaluation)

**Files:**
- Create: `src/signalagent/security/__init__.py`
- Create: `src/signalagent/security/engine.py`
- Create: `tests/unit/security/__init__.py`
- Create: `tests/unit/security/test_engine.py`

- [ ] **Step 1: Write failing tests for PolicyEngine**

Create `tests/unit/security/__init__.py` (empty file).

Create `tests/unit/security/test_engine.py`:

```python
"""Unit tests for PolicyEngine -- pure rules evaluation."""

import pytest

from signalagent.core.models import AgentPolicy
from signalagent.security.engine import PolicyEngine


class TestCheckToolAccess:
    def test_no_policy_allows(self):
        engine = PolicyEngine(policies=[])
        decision = engine.check_tool_access("researcher", "web_search")
        assert decision.allowed is True
        assert decision.rule == "no_policy"

    def test_no_tool_rules_allows(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher"]),
        ])
        decision = engine.check_tool_access("researcher", "web_search")
        assert decision.allowed is True
        assert decision.rule == "no_tool_rules"

    def test_allowed_tool(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search", "file_system"]),
        ])
        decision = engine.check_tool_access("researcher", "web_search")
        assert decision.allowed is True
        assert "allow_tools" in decision.rule

    def test_denied_tool(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search"]),
        ])
        decision = engine.check_tool_access("researcher", "bash")
        assert decision.allowed is False
        assert "deny" in decision.rule
        assert "bash" in decision.rule

    def test_different_agents_different_rules(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search"]),
            AgentPolicy(agent="coder", allow_tools=["bash"]),
        ])
        assert engine.check_tool_access("researcher", "bash").allowed is False
        assert engine.check_tool_access("coder", "bash").allowed is True


class TestFilterMemoryAgents:
    def test_no_policy_returns_none(self):
        engine = PolicyEngine(policies=[])
        assert engine.filter_memory_agents("researcher") is None

    def test_no_memory_rules_returns_none(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search"]),
        ])
        assert engine.filter_memory_agents("researcher") is None

    def test_returns_allowed_set(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher", "shared"]),
        ])
        result = engine.filter_memory_agents("researcher")
        assert result == {"researcher", "shared"}

    def test_different_agents_different_scopes(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher"]),
            AgentPolicy(agent="coder", allow_memory_read=["coder", "researcher", "shared"]),
        ])
        assert engine.filter_memory_agents("researcher") == {"researcher"}
        assert engine.filter_memory_agents("coder") == {"coder", "researcher", "shared"}


class TestHasPolicy:
    def test_has_policy_true(self):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher"),
        ])
        assert engine.has_policy("researcher") is True

    def test_has_policy_false(self):
        engine = PolicyEngine(policies=[])
        assert engine.has_policy("researcher") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/security/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.security'`

- [ ] **Step 3: Implement PolicyEngine**

Create `src/signalagent/security/__init__.py` (empty file).

Create `src/signalagent/security/engine.py`:

```python
"""PolicyEngine -- pure rules evaluation, no I/O."""

from __future__ import annotations

from typing import NamedTuple

from signalagent.core.models import AgentPolicy


class PolicyDecision(NamedTuple):
    """Result of a policy check: allowed + which rule matched."""

    allowed: bool
    rule: str


class PolicyEngine:
    """Evaluates declarative policy rules.

    Pure logic, no I/O, no dependencies beyond the rules themselves.
    Shared by PolicyHook (tool access) and PolicyMemoryReader (memory scoping).
    """

    def __init__(self, policies: list[AgentPolicy]) -> None:
        self._by_agent: dict[str, AgentPolicy] = {
            p.agent: p for p in policies
        }

    def check_tool_access(
        self, agent: str, tool_name: str,
    ) -> PolicyDecision:
        """Check whether an agent is allowed to use a tool."""
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

        The keyword "shared" in the returned set matches memories with
        type=MemoryType.SHARED. All other entries are agent names.
        """
        policy = self._by_agent.get(agent)
        if policy is None or policy.allow_memory_read is None:
            return None
        return set(policy.allow_memory_read)

    def has_policy(self, agent: str) -> bool:
        """Check whether an agent has any policy entry."""
        return agent in self._by_agent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/security/test_engine.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/security/__init__.py src/signalagent/security/engine.py tests/unit/security/__init__.py tests/unit/security/test_engine.py
git commit -m "feat(security): add PolicyEngine for pure rules evaluation"
```

---

### Task 3: AuditLogger (JSONL Writer)

**Files:**
- Create: `src/signalagent/security/audit.py`
- Create: `tests/unit/security/test_audit.py`

- [ ] **Step 1: Write failing tests for AuditLogger**

Create `tests/unit/security/test_audit.py`:

```python
"""Unit tests for AuditLogger -- JSONL append + deduplication."""

import json

import pytest

from signalagent.security.audit import AuditEvent, AuditLogger


class TestAuditEvent:
    def test_construction(self):
        event = AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        )
        assert event.event_type == "tool_call"
        assert event.agent == "researcher"

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            AuditEvent(
                timestamp="2026-04-03T12:00:00+00:00",
                event_type="tool_call",
                agent="researcher",
                detail={},
                bogus="bad",
            )


class TestAuditLoggerLog:
    def test_creates_audit_file(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        ))
        audit_file = tmp_path / "logs" / "audit.jsonl"
        assert audit_file.exists()

    def test_appends_jsonl(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        ))
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:01:00+00:00",
            event_type="policy_denial",
            agent="researcher",
            detail={"tool": "bash"},
        ))
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "tool_call"
        assert json.loads(lines[1])["event_type"] == "policy_denial"

    def test_detail_preserved(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="policy_denial",
            agent="coder",
            detail={"tool": "bash", "rule": "deny:tool:bash"},
        ))
        entry = json.loads(
            (tmp_path / "logs" / "audit.jsonl").read_text().strip(),
        )
        assert entry["detail"]["rule"] == "deny:tool:bash"


class TestAuditLoggerWarningDedup:
    def test_warn_no_policy_logs_once(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("researcher")
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event_type"] == "warning"
        assert "researcher" in entry["detail"]["message"]

    def test_warn_different_agents(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("coder")
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/security/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.security.audit'`

- [ ] **Step 3: Implement AuditLogger**

Create `src/signalagent/security/audit.py`:

```python
"""AuditLogger -- structured JSONL audit trail for policy decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    """A single audit trail entry."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    event_type: str
    agent: str
    detail: dict[str, Any]


class AuditLogger:
    """Appends audit events to a JSONL file.

    Same pattern as LogToolCallsHook (JSONL append) and
    SessionManager (file-based persistence). Pure I/O, no logic.
    """

    def __init__(self, audit_dir: Path) -> None:
        self._audit_dir = audit_dir
        self._warned_agents: set[str] = set()

    def log(self, event: AuditEvent) -> None:
        """Append a single event to audit.jsonl."""
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        path = self._audit_dir / "audit.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def warn_no_policy(self, agent: str) -> None:
        """Log 'no policy configured' warning, deduplicated per agent.

        Tracked in-memory -- resets per process lifetime, not persisted.
        """
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/security/test_audit.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/security/audit.py tests/unit/security/test_audit.py
git commit -m "feat(security): add AuditLogger with JSONL append and warning dedup"
```

---

### Task 4: Hook Protocol + HookExecutor Changes

**Files:**
- Modify: `src/signalagent/hooks/protocol.py`
- Modify: `src/signalagent/hooks/executor.py`
- Modify: `src/signalagent/hooks/builtins/log_tool_calls.py`
- Modify: `tests/unit/hooks/test_executor.py`

- [ ] **Step 1: Write failing tests for agent passing and fail_closed**

Add these test classes to the bottom of `tests/unit/hooks/test_executor.py`:

```python
class FailClosedBeforeHook:
    @property
    def name(self):
        return "fail_closed_before"
    @property
    def fail_closed(self):
        return True
    async def before_tool_call(self, tool_name, arguments, agent=""):
        raise RuntimeError("safety hook crashed")
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class FailClosedAfterHook:
    @property
    def name(self):
        return "fail_closed_after"
    @property
    def fail_closed(self):
        return True
    async def before_tool_call(self, tool_name, arguments, agent=""):
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        raise RuntimeError("safety after hook crashed")


class AgentAwareHook:
    def __init__(self):
        self.agents_seen: list[str] = []
    @property
    def name(self):
        return "agent_aware"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        self.agents_seen.append(agent)
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class TestHookExecutorFailClosed:
    @pytest.mark.asyncio
    async def test_fail_closed_before_blocks_call(self, inner_executor):
        registry = HookRegistry()
        registry.register(FailClosedBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.error is not None
        assert "Policy hook error" in result.error
        inner_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_open_before_allows_call(self, inner_executor):
        """Existing CrashingBeforeHook (no fail_closed) still fails open."""
        registry = HookRegistry()
        registry.register(CrashingBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
        inner_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_closed_after_logs_error(self, inner_executor):
        """Fail-closed after_tool_call escalates log level but doesn't block result."""
        registry = HookRegistry()
        registry.register(FailClosedAfterHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        # Tool already executed, result still returned
        assert result.output == "tool result"


class TestHookExecutorAgentPassing:
    @pytest.mark.asyncio
    async def test_agent_passed_to_hooks(self, inner_executor):
        registry = HookRegistry()
        hook = AgentAwareHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry, agent="researcher")
        await executor("file_system", {})
        assert hook.agents_seen == ["researcher"]

    @pytest.mark.asyncio
    async def test_agent_defaults_to_empty(self, inner_executor):
        registry = HookRegistry()
        hook = AgentAwareHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {})
        assert hook.agents_seen == [""]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/hooks/test_executor.py::TestHookExecutorFailClosed -v`
Expected: FAIL (FailClosedBeforeHook passes agent kwarg but HookExecutor doesn't pass it)

- [ ] **Step 3: Update Hook protocol**

Replace the entire contents of `src/signalagent/hooks/protocol.py`:

```python
"""Hook protocol -- interface every hook must implement."""
from __future__ import annotations
from typing import Protocol
from signalagent.core.models import ToolResult


class Hook(Protocol):
    """Protocol for tool call hooks.

    Hooks observe and optionally block tool calls. They cannot modify
    arguments or results.

    Failure mode: hooks default to fail-open (crash = log + continue).
    Safety-critical hooks (e.g., PolicyHook) set a ``fail_closed``
    property to ``True`` so a crash blocks the call rather than
    allowing it through.  The HookExecutor checks for this via
    ``getattr(hook, 'fail_closed', False)``.
    """

    @property
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Return None to allow, or ToolResult with error to block."""
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None:
        """Observe only. Always fires, including on blocked calls."""
        ...
```

- [ ] **Step 4: Update HookExecutor**

Replace the entire contents of `src/signalagent/hooks/executor.py`:

```python
"""HookExecutor -- wraps a ToolExecutor with before/after hook lifecycle."""
from __future__ import annotations
import logging
from signalagent.core.models import ToolResult
from signalagent.core.protocols import ToolExecutor
from signalagent.hooks.registry import HookRegistry

logger = logging.getLogger(__name__)


class HookExecutor:
    """Wraps any ToolExecutor with before/after hook lifecycle.

    Implements the ToolExecutor protocol (async callable).

    Lifecycle:
    1. Run before_tool_call on each hook. If any returns a ToolResult,
       stop and use it (blocked). Set blocked=True.
    2. If not blocked: call inner executor. Set blocked=False.
    3. Run after_tool_call on all hooks. Always fires. Pass blocked flag.
    4. Return result.

    Failure modes:
    - fail-open (default): hook crash is logged and skipped.
    - fail-closed: hook crash blocks the call. Activated when a hook
      has a ``fail_closed`` property that returns True.
    """

    def __init__(
        self,
        inner: ToolExecutor,
        registry: HookRegistry,
        agent: str = "",
    ) -> None:
        self._inner = inner
        self._registry = registry
        self._agent = agent

    async def __call__(self, tool_name: str, arguments: dict) -> ToolResult:
        hooks = self._registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(
                    tool_name, arguments, agent=self._agent,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    return ToolResult(
                        output="", error=f"Policy hook error: {e}",
                    )
                logger.warning(
                    "Hook '%s' before_tool_call raised (fail open): %s",
                    hook.name, e,
                )
                continue
            if before_result is not None:
                result = before_result
                blocked = True
                break

        # Execute tool if not blocked
        if not blocked:
            result = await self._inner(tool_name, arguments)

        assert result is not None

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(
                    tool_name, arguments, result, blocked,
                    agent=self._agent,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    logger.error(
                        "Fail-closed hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )
                else:
                    logger.warning(
                        "Hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )

        return result
```

- [ ] **Step 5: Update LogToolCallsHook signatures**

In `src/signalagent/hooks/builtins/log_tool_calls.py`, update the two method signatures.

Change `before_tool_call`:
```python
    async def before_tool_call(self, tool_name: str, arguments: dict, agent: str = "") -> ToolResult | None:
```

Change `after_tool_call`:
```python
    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult, blocked: bool, agent: str = "",
    ) -> None:
```

The method bodies stay the same -- they accept the parameter and ignore it.

- [ ] **Step 6: Run all hook tests**

Run: `pytest tests/unit/hooks/ -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/hooks/protocol.py src/signalagent/hooks/executor.py src/signalagent/hooks/builtins/log_tool_calls.py tests/unit/hooks/test_executor.py
git commit -m "feat(hooks): add agent param and fail_closed support to hook lifecycle"
```

---

### Task 5: WorktreeProxy ISOLATED Mode Updates

**Files:**
- Modify: `src/signalagent/worktrees/proxy.py:104-142`
- Modify: `tests/unit/worktrees/test_proxy.py`

- [ ] **Step 1: Write failing tests for agent passing and fail_closed in ISOLATED mode**

Read the existing `tests/unit/worktrees/test_proxy.py` to find where to add tests. Add a new test class at the bottom:

```python
class TestIsolatedModeAgentAndFailClosed:
    """WorktreeProxy passes agent name to hooks and respects fail_closed in ISOLATED mode."""

    @pytest.mark.asyncio
    async def test_hooks_receive_agent_name(self, proxy_with_hooks):
        """Hooks in ISOLATED mode receive the agent name."""
        proxy, registry = proxy_with_hooks

        class AgentCapture:
            def __init__(self):
                self.agents = []
            @property
            def name(self):
                return "agent_capture"
            async def before_tool_call(self, tool_name, arguments, agent=""):
                self.agents.append(agent)
                return None
            async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
                pass

        hook = AgentCapture()
        registry.register(hook)

        # Trigger ISOLATED mode with a write
        await proxy("file_system", {"operation": "write", "path": "test.py", "content": "x"})
        assert hook.agents == [proxy._agent_name]

    @pytest.mark.asyncio
    async def test_fail_closed_before_blocks_in_isolated(self, proxy_with_hooks):
        """Fail-closed hook crash in ISOLATED before_tool_call blocks the call."""
        proxy, registry = proxy_with_hooks

        class FailClosedCrasher:
            @property
            def name(self):
                return "crasher"
            @property
            def fail_closed(self):
                return True
            async def before_tool_call(self, tool_name, arguments, agent=""):
                raise RuntimeError("safety crash")
            async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
                pass

        registry.register(FailClosedCrasher())

        # Trigger ISOLATED mode
        await proxy("file_system", {"operation": "write", "path": "a.py", "content": "x"})
        # Second call is in ISOLATED mode -- hook should block
        result = await proxy("file_system", {"operation": "read", "path": "a.py"})
        assert result.error is not None
        assert "Policy hook error" in result.error
```

> **Note for implementer:** The `proxy_with_hooks` fixture may not exist yet. Check the existing test file for fixture patterns. If it doesn't exist, create a fixture that returns a `(WorktreeProxy, HookRegistry)` tuple configured for testing. The proxy needs a real `WorktreeManager`, a `HookRegistry`, and a `WorktreeManifest`. Follow the existing fixture patterns in the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/worktrees/test_proxy.py::TestIsolatedModeAgentAndFailClosed -v`
Expected: FAIL (hooks don't receive agent param yet)

- [ ] **Step 3: Update WorktreeProxy._execute_isolated()**

In `src/signalagent/worktrees/proxy.py`, replace the `_execute_isolated` method (lines 104-142):

```python
    async def _execute_isolated(self, tool_name: str, arguments: dict) -> ToolResult:
        """Execute file_system call against worktree, calling hooks directly.

        Hook lifecycle mirrors HookExecutor.__call__: before hooks run first,
        if any blocks we skip the tool, after hooks always fire.
        Passes agent name and respects fail_closed.
        """
        hooks = self._hook_registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(
                    tool_name, arguments, agent=self._agent_name,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    return ToolResult(
                        output="", error=f"Policy hook error: {e}",
                    )
                logger.warning(
                    "Hook '%s' before_tool_call raised (fail open): %s",
                    hook.name, e,
                )
                continue
            if before_result is not None:
                result = before_result
                blocked = True
                break

        # Execute against worktree tool if not blocked
        if not blocked:
            result = await self._execute_in_worktree(tool_name, arguments)

        assert result is not None

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(
                    tool_name, arguments, result, blocked,
                    agent=self._agent_name,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    logger.error(
                        "Fail-closed hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )
                else:
                    logger.warning(
                        "Hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )

        return result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/worktrees/test_proxy.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/worktrees/proxy.py tests/unit/worktrees/test_proxy.py
git commit -m "feat(worktrees): pass agent name and respect fail_closed in ISOLATED hooks"
```

---

### Task 6: PolicyHook (Fail-Closed Tool Enforcement)

**Files:**
- Create: `src/signalagent/security/policy_hook.py`
- Create: `tests/unit/security/test_policy_hook.py`

- [ ] **Step 1: Write failing tests for PolicyHook**

Create `tests/unit/security/test_policy_hook.py`:

```python
"""Unit tests for PolicyHook -- fail-closed tool enforcement + audit."""

import json

import pytest

from signalagent.core.models import AgentPolicy, ToolResult
from signalagent.security.audit import AuditLogger
from signalagent.security.engine import PolicyEngine
from signalagent.security.policy_hook import PolicyHook


@pytest.fixture
def policy_engine():
    return PolicyEngine(policies=[
        AgentPolicy(agent="researcher", allow_tools=["web_search", "file_system"]),
        AgentPolicy(agent="coder", allow_tools=["file_system", "bash"]),
    ])


@pytest.fixture
def audit_logger(tmp_path):
    return AuditLogger(audit_dir=tmp_path / "logs")


@pytest.fixture
def audit_file(tmp_path):
    return tmp_path / "logs" / "audit.jsonl"


@pytest.fixture
def hook(policy_engine, audit_logger):
    return PolicyHook(engine=policy_engine, audit=audit_logger)


class TestPolicyHookProperties:
    def test_name(self, hook):
        assert hook.name == "policy"

    def test_fail_closed(self, hook):
        assert hook.fail_closed is True


class TestPolicyHookBeforeToolCall:
    @pytest.mark.asyncio
    async def test_allows_authorized_tool(self, hook):
        result = await hook.before_tool_call(
            "web_search", {"query": "test"}, agent="researcher",
        )
        assert result is None  # allowed

    @pytest.mark.asyncio
    async def test_blocks_unauthorized_tool(self, hook):
        result = await hook.before_tool_call(
            "bash", {"command": "rm -rf"}, agent="researcher",
        )
        assert result is not None
        assert result.error is not None
        assert "Policy denied" in result.error

    @pytest.mark.asyncio
    async def test_denial_logged_to_audit(self, hook, audit_file):
        await hook.before_tool_call("bash", {}, agent="researcher")
        lines = audit_file.read_text().strip().split("\n")
        denial = json.loads(lines[-1])
        assert denial["event_type"] == "policy_denial"
        assert denial["agent"] == "researcher"
        assert denial["detail"]["tool"] == "bash"

    @pytest.mark.asyncio
    async def test_no_policy_warns(self, hook, audit_file):
        await hook.before_tool_call("anything", {}, agent="unknown_agent")
        lines = audit_file.read_text().strip().split("\n")
        warning = json.loads(lines[0])
        assert warning["event_type"] == "warning"
        assert "unknown_agent" in warning["detail"]["message"]

    @pytest.mark.asyncio
    async def test_no_policy_allows(self, hook):
        """Agent with no policy entry is allowed (default-allow)."""
        result = await hook.before_tool_call("bash", {}, agent="unknown_agent")
        assert result is None


class TestPolicyHookAfterToolCall:
    @pytest.mark.asyncio
    async def test_logs_tool_call_event(self, hook, audit_file):
        await hook.before_tool_call("web_search", {}, agent="researcher")
        await hook.after_tool_call(
            "web_search", {}, ToolResult(output="result"), blocked=False,
            agent="researcher",
        )
        lines = audit_file.read_text().strip().split("\n")
        tool_event = json.loads(lines[-1])
        assert tool_event["event_type"] == "tool_call"
        assert tool_event["detail"]["tool"] == "web_search"
        assert tool_event["detail"]["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_logs_blocked_by_other(self, hook, audit_file):
        await hook.before_tool_call("web_search", {}, agent="researcher")
        await hook.after_tool_call(
            "web_search", {}, ToolResult(output="", error="blocked"), blocked=True,
            agent="researcher",
        )
        lines = audit_file.read_text().strip().split("\n")
        tool_event = json.loads(lines[-1])
        assert tool_event["detail"]["blocked_by_other"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/security/test_policy_hook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.security.policy_hook'`

- [ ] **Step 3: Implement PolicyHook**

Create `src/signalagent/security/policy_hook.py`:

```python
"""PolicyHook -- fail-closed tool access enforcement with audit trail."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from signalagent.core.models import ToolResult
from signalagent.security.audit import AuditEvent, AuditLogger
from signalagent.security.engine import PolicyEngine


class PolicyHook:
    """Enforces tool access policies. Fail-closed: a crash blocks the call.

    Produces two audit event types:
    - policy_denial: tool access blocked by policy rule
    - tool_call: tool executed (logged in after_tool_call)
    Also emits deduplicated warnings for agents without policy entries.
    """

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
            return ToolResult(
                output="", error=f"Policy denied: {tool_name}",
            )
        return None

    async def after_tool_call(
        self, tool_name: str, arguments: dict,
        result: ToolResult, blocked: bool, agent: str = "",
    ) -> None:
        duration_ms = 0
        if self._pending_start is not None:
            duration_ms = int(
                (time.monotonic() - self._pending_start) * 1000,
            )
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/security/test_policy_hook.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/security/policy_hook.py tests/unit/security/test_policy_hook.py
git commit -m "feat(security): add PolicyHook for fail-closed tool enforcement"
```

---

### Task 7: PolicyMemoryReader (Memory Scoping Wrapper)

**Files:**
- Create: `src/signalagent/security/memory_filter.py`
- Create: `tests/unit/security/test_memory_filter.py`

- [ ] **Step 1: Write failing tests for PolicyMemoryReader**

Create `tests/unit/security/test_memory_filter.py`:

```python
"""Unit tests for PolicyMemoryReader -- memory scoping wrapper."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from signalagent.core.models import AgentPolicy, Memory
from signalagent.core.types import MemoryType
from signalagent.security.audit import AuditLogger
from signalagent.security.engine import PolicyEngine
from signalagent.security.memory_filter import PolicyMemoryReader


def _make_memory(agent: str, memory_type: MemoryType = MemoryType.LEARNING) -> Memory:
    now = datetime.now(timezone.utc)
    return Memory(
        id=f"mem_{agent[:4]}",
        agent=agent,
        type=memory_type,
        tags=["test"],
        content=f"Memory from {agent}",
        created=now,
        updated=now,
        accessed=now,
    )


@pytest.fixture
def audit_logger(tmp_path):
    return AuditLogger(audit_dir=tmp_path / "logs")


@pytest.fixture
def audit_file(tmp_path):
    return tmp_path / "logs" / "audit.jsonl"


class TestPolicyMemoryReaderPassThrough:
    @pytest.mark.asyncio
    async def test_no_policy_passes_through(self, audit_logger):
        """Agent with no policy gets unfiltered results."""
        engine = PolicyEngine(policies=[])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[_make_memory("prime")])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        results = await reader.search(tags=["test"])
        assert len(results) == 1
        inner.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_memory_rules_passes_through(self, audit_logger):
        """Agent with only tool rules gets unfiltered memory results."""
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_tools=["web_search"]),
        ])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[_make_memory("prime")])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        results = await reader.search()
        assert len(results) == 1


class TestPolicyMemoryReaderFiltering:
    @pytest.mark.asyncio
    async def test_allows_own_agent_memories(self, audit_logger):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher"]),
        ])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[
            _make_memory("researcher"),
            _make_memory("coder"),
        ])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        results = await reader.search()
        assert len(results) == 1
        assert results[0].agent == "researcher"

    @pytest.mark.asyncio
    async def test_allows_shared_keyword(self, audit_logger):
        """The 'shared' keyword matches memories with type=SHARED."""
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher", "shared"]),
        ])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[
            _make_memory("researcher"),
            _make_memory("shared_pool", MemoryType.SHARED),
            _make_memory("coder"),
        ])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        results = await reader.search()
        assert len(results) == 2
        types = {r.agent for r in results}
        assert "researcher" in types
        assert "shared_pool" in types  # allowed by SHARED type match

    @pytest.mark.asyncio
    async def test_filters_denied_agents(self, audit_logger):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher"]),
        ])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[
            _make_memory("coder"),
            _make_memory("admin"),
        ])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        results = await reader.search()
        assert len(results) == 0


class TestPolicyMemoryReaderAudit:
    @pytest.mark.asyncio
    async def test_denial_logged(self, audit_logger, audit_file):
        engine = PolicyEngine(policies=[
            AgentPolicy(agent="researcher", allow_memory_read=["researcher"]),
        ])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[_make_memory("coder")])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        await reader.search()

        lines = audit_file.read_text().strip().split("\n")
        denial = json.loads(lines[0])
        assert denial["event_type"] == "policy_denial"
        assert denial["agent"] == "researcher"
        assert denial["detail"]["denied"] == "memory_read"
        assert denial["detail"]["memory_agent"] == "coder"

    @pytest.mark.asyncio
    async def test_pass_through_params(self, audit_logger):
        """All search parameters are forwarded to the inner reader."""
        engine = PolicyEngine(policies=[])
        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[])

        reader = PolicyMemoryReader(
            inner=inner, engine=engine, audit=audit_logger, agent="researcher",
        )
        await reader.search(
            tags=["python"], agent="prime", memory_type="learning",
            limit=5, touch=True, query="error handling",
        )
        inner.search.assert_called_once_with(
            tags=["python"], agent="prime", memory_type="learning",
            limit=5, touch=True, query="error handling",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/security/test_memory_filter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.security.memory_filter'`

- [ ] **Step 3: Implement PolicyMemoryReader**

Create `src/signalagent/security/memory_filter.py`:

```python
"""PolicyMemoryReader -- memory scoping wrapper using policy rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from signalagent.security.audit import AuditEvent, AuditLogger
from signalagent.security.engine import PolicyEngine


class PolicyMemoryReader:
    """Wraps a MemoryReaderProtocol, filtering results by policy rules.

    Implements MemoryReaderProtocol. Injected at bootstrap per agent.
    When filter_memory_agents() returns None, passes through unchanged.
    Otherwise, post-retrieval filtering removes unauthorized memories
    and logs policy_denial events.

    The keyword "shared" in allow_memory_read matches memories with
    type=MemoryType.SHARED (the shared memory pool), not an agent
    named "shared."
    """

    def __init__(
        self,
        inner: Any,
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
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        touch: bool = False,
        query: str | None = None,
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
                        "rule": (
                            f"allow_memory_read excludes {memory.agent}"
                        ),
                    },
                ))
        return filtered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/security/test_memory_filter.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/security/memory_filter.py tests/unit/security/test_memory_filter.py
git commit -m "feat(security): add PolicyMemoryReader for memory scoping"
```

---

### Task 8: Bootstrap Wiring

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for bootstrap policy wiring**

Add to the bottom of `tests/unit/runtime/test_bootstrap.py`:

```python
from signalagent.core.models import AgentPolicy, SecurityConfig
from signalagent.security.memory_filter import PolicyMemoryReader


@pytest.fixture
def profile_with_policies():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="researcher", skill="Research",
                talks_to=["prime"], plugins=["file_system"],
            ),
        ],
        security=SecurityConfig(policies=[
            AgentPolicy(
                agent="researcher",
                allow_tools=["file_system"],
                allow_memory_read=["researcher", "shared"],
            ),
        ]),
    )


@pytest.fixture
def profile_without_policies():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="researcher", skill="Research",
                talks_to=["prime"], plugins=["file_system"],
            ),
        ],
    )


class TestPolicyBootstrap:
    @pytest.mark.asyncio
    async def test_policy_memory_reader_injected(
        self, tmp_path, config, profile_with_policies, monkeypatch,
    ):
        """When policies exist, agents get PolicyMemoryReader wrappers."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_policies)

        researcher = host.get("researcher")
        assert isinstance(
            researcher._memory_reader,  # type: ignore[union-attr]
            PolicyMemoryReader,
        )

        prime = host.get(PRIME_AGENT)
        assert isinstance(
            prime._memory_reader,  # type: ignore[union-attr]
            PolicyMemoryReader,
        )

    @pytest.mark.asyncio
    async def test_no_policy_raw_engine(
        self, tmp_path, config, profile_without_policies, monkeypatch,
    ):
        """Without policies, agents get the raw MemoryEngine."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_without_policies)

        researcher = host.get("researcher")
        assert not isinstance(
            researcher._memory_reader,  # type: ignore[union-attr]
            PolicyMemoryReader,
        )

    @pytest.mark.asyncio
    async def test_policy_blocks_unauthorized_tool(
        self, tmp_path, config, profile_with_policies, monkeypatch,
    ):
        """End-to-end: PolicyHook blocks a tool call denied by policy."""
        tc = ToolCallRequest(
            id="call_1", name="bash",
            arguments={"command": "echo hello"},
        )
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("bash was denied"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_policies)
        result = await executor.run("run a shell command")

        # The runner should have received a denial error for bash
        assert result.content == "bash was denied"

    @pytest.mark.asyncio
    async def test_audit_file_written(
        self, tmp_path, config, profile_with_policies, monkeypatch,
    ):
        """Bootstrap creates audit logger and events are written."""
        tc = ToolCallRequest(
            id="call_1", name="file_system",
            arguments={"operation": "list", "path": "."},
        )
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Listed files"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_policies)
        await executor.run("list files")

        audit_file = tmp_path / "logs" / "audit.jsonl"
        assert audit_file.exists()
        import json
        lines = audit_file.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines]
        event_types = [e["event_type"] for e in events]
        assert "tool_call" in event_types
```

Also add the `SecurityConfig` and `AgentPolicy` imports to the import block at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/runtime/test_bootstrap.py::TestPolicyBootstrap -v`
Expected: FAIL (bootstrap doesn't create security components yet)

- [ ] **Step 3: Update bootstrap**

In `src/signalagent/runtime/bootstrap.py`, add imports at the top:

```python
from signalagent.security.audit import AuditLogger
from signalagent.security.engine import PolicyEngine
from signalagent.security.memory_filter import PolicyMemoryReader
from signalagent.security.policy_hook import PolicyHook
```

Then modify the `bootstrap` function body. After the existing memory engine initialization (after `await engine.initialize()`), add the security layer setup:

```python
    # Security layer
    policy_engine = PolicyEngine(profile.security.policies)
    audit_logger = AuditLogger(instance_dir / "logs")
```

After the existing hook registry setup (after the hook loading loop), add conditional PolicyHook registration:

```python
    # PolicyHook -- conditional: only when policies exist
    if profile.security.policies:
        policy_hook = PolicyHook(engine=policy_engine, audit=audit_logger)
        hook_registry.register(policy_hook)
```

Add the memory reader helper before agent creation:

```python
    # Memory reader: policy-filtered or raw engine
    def make_memory_reader(agent_name: str):
        if profile.security.policies:
            return PolicyMemoryReader(
                inner=engine, engine=policy_engine,
                audit=audit_logger, agent=agent_name,
            )
        return engine
```

Update the PrimeAgent creation to use the helper:

```python
    prime = PrimeAgent(
        identity=profile.prime.identity, ai=ai, host=host, bus=bus,
        memory_reader=make_memory_reader("prime"), model=model_name,
    )
```

Update each HookExecutor creation in the micro-agent loop to include the agent name. For the `can_spawn_subs` path, change:

```python
            agent_executor = HookExecutor(
                inner=agent_inner, registry=hook_registry,
                agent=micro_config.name,
            )
```

For the non-spawn path, replace the shared `tool_executor` usage with a per-agent HookExecutor:

```python
        else:
            agent_hook_executor = HookExecutor(
                inner=inner_executor, registry=hook_registry,
                agent=micro_config.name,
            )
            worktree_proxy = WorktreeProxy(
                inner=agent_hook_executor,
                hook_registry=hook_registry,
                worktree_manager=worktree_manager,
                manifest=worktree_manifest,
                workspace_root=instance_dir,
                instance_dir=instance_dir,
                agent_name=micro_config.name,
            )
```

Update MicroAgent creation to use `make_memory_reader`:

```python
        agent = MicroAgent(
            config=micro_config, runner=runner,
            memory_reader=make_memory_reader(micro_config.name),
            model=model_name,
            worktree_proxy=worktree_proxy,
        )
```

> **Implementation note:** The shared `tool_executor = HookExecutor(inner=inner_executor, registry=hook_registry)` defined before the loop is still used for the `can_spawn_subs` path's inner executor chain. Keep it, but the non-spawn path no longer references it. The `Wrap with hooks` comment and `tool_executor` variable stay for the spawn path.

- [ ] **Step 4: Run all bootstrap tests**

Run: `pytest tests/unit/runtime/test_bootstrap.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat(bootstrap): wire PolicyEngine, AuditLogger, PolicyHook, and PolicyMemoryReader"
```

---

### Task 9: Version Bump + Roadmap Update

**Files:**
- Modify: `VERSION`
- Modify: `docs/dev/roadmap.md`

- [ ] **Step 1: Bump version**

Update `VERSION` to:

```
0.14.0
```

- [ ] **Step 2: Update roadmap**

In `docs/dev/roadmap.md`, change the Phase 10 row from:

```
| 10 | Safety + Docker + Full CLI | Planned | Policy engine, containerization, all commands |
```

To two rows:

```
| 10a | Policy + Audit | Complete | Declarative policies, audit trail, fail-closed hooks |
| 10b | Docker + Full CLI | Planned | Containerization, all commands |
```

- [ ] **Step 3: Commit**

```bash
git add VERSION docs/dev/roadmap.md
git commit -m "chore: bump version to 0.14.0 for Phase 10a, update roadmap"
```

---

## Self-Review Checklist

### Spec Coverage
| Spec Criterion | Task |
|---|---|
| 1. PolicyEngine.check_tool_access() | Task 2 |
| 2. PolicyEngine.filter_memory_agents() | Task 2 |
| 3. PolicyEngine.has_policy() | Task 2 |
| 4. "shared" keyword documented | Task 2 (docstring), Task 7 (docstring + test) |
| 5. AuditLogger.log() appends JSONL | Task 3 |
| 6. Three event types | Task 3 + Task 6 |
| 7. Warning deduplication | Task 3 |
| 8. PolicyHook.fail_closed = True | Task 6 |
| 9. before_tool_call blocks + logs denial | Task 6 |
| 10. after_tool_call logs tool_call event | Task 6 |
| 11. PolicyHook conditional registration | Task 8 |
| 12. Hook protocol gains agent param | Task 4 |
| 13. HookExecutor gains agent param | Task 4 |
| 14. fail_closed check in HookExecutor | Task 4 |
| 15. LogToolCallsHook signature update | Task 4 |
| 16. PolicyMemoryReader implements protocol | Task 7 |
| 17. Post-retrieval filtering | Task 7 |
| 18. Filtered memories produce denial events | Task 7 |
| 19. filter_memory_agents None = pass-through | Task 7 |
| 20. AgentPolicy + SecurityConfig on Profile | Task 1 |
| 21. Bootstrap creates all security components | Task 8 |
| 22. Per-agent HookExecutor | Task 8 |
| 23. make_memory_reader helper | Task 8 |
| 24. All existing tests pass | Task 8 (full suite run) |
| 25. signal talk/chat unchanged | Task 8 (existing bootstrap tests) |
| 26. Profiles without security work | Task 8 (profile_without_policies test) |
| 27. WorktreeProxy ISOLATED agent + fail_closed | Task 5 |

### Placeholder Scan
No TBD, TODO, or "implement later" found. All code blocks are complete.

### Type Consistency
- `AgentPolicy` -- defined in Task 1, used in Tasks 2, 6, 7, 8. Same import path everywhere.
- `PolicyEngine` -- defined in Task 2, used in Tasks 6, 7, 8. Same constructor signature.
- `AuditLogger` / `AuditEvent` -- defined in Task 3, used in Tasks 6, 7, 8. Same interface.
- `PolicyHook` -- defined in Task 6, used in Task 8. Same constructor.
- `PolicyMemoryReader` -- defined in Task 7, used in Task 8. Same constructor.
- Hook protocol `agent: str = ""` -- consistent across Tasks 4, 5, 6.
