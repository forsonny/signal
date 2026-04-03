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
        """Create a policy hook backed by *engine* and *audit*.

        Args:
            engine: Policy engine for tool-access decisions.
            audit: Audit logger for recording decisions and tool calls.
        """
        self._engine = engine
        self._audit = audit
        self._pending_start: float | None = None
        self._pending_agent: str = ""

    @property
    def name(self) -> str:
        """Return the hook identifier (``"policy"``)."""
        return "policy"

    @property
    def fail_closed(self) -> bool:
        """Return ``True`` -- a crash in this hook blocks the tool call."""
        return True

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Evaluate policy before a tool executes.

        Records the start time for duration tracking, emits a warning if
        the agent has no policy entry, and blocks the call with a
        ``ToolResult`` error when the policy denies access.

        Args:
            tool_name: Name of the tool about to be invoked.
            arguments: Arguments the tool will receive.
            agent: Name of the calling agent (empty string if unknown).

        Returns:
            ``None`` if the call is allowed, or a ``ToolResult`` with an
            error message if the policy denies access.
        """
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
        """Log a ``tool_call`` audit event after tool execution completes.

        Args:
            tool_name: Name of the tool that was invoked.
            arguments: Arguments the tool received.
            result: The ``ToolResult`` returned by the tool.
            blocked: Whether a *different* hook blocked this call.
            agent: Name of the calling agent.
        """
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
