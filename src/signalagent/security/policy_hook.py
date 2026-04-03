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
