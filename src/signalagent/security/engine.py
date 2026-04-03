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
