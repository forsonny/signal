"""PolicyEngine -- pure rules evaluation, no I/O."""

from __future__ import annotations

from typing import NamedTuple

from signalagent.core.models import AgentPolicy


class PolicyDecision(NamedTuple):
    """Result of a policy check: allowed + which rule matched.

    Attributes:
        allowed: Whether the action is permitted.
        rule: Human-readable identifier of the rule that produced
            this decision (e.g. ``"allow_tools:read_file"``).
    """

    allowed: bool
    rule: str


class PolicyEngine:
    """Evaluates declarative policy rules.

    Pure logic, no I/O, no dependencies beyond the rules themselves.
    Shared by PolicyHook (tool access) and PolicyMemoryReader (memory scoping).
    """

    def __init__(self, policies: list[AgentPolicy]) -> None:
        """Initialise the engine with a list of agent policy rules.

        Args:
            policies: Declarative policy entries, one per agent. Duplicate
                agent names silently overwrite earlier entries.
        """
        self._by_agent: dict[str, AgentPolicy] = {
            p.agent: p for p in policies
        }

    def check_tool_access(
        self, agent: str, tool_name: str,
    ) -> PolicyDecision:
        """Check whether an agent is allowed to use a tool.

        Args:
            agent: Name of the agent requesting access.
            tool_name: Name of the tool the agent wants to invoke.

        Returns:
            A ``PolicyDecision`` indicating whether access is allowed
            and which rule produced the decision.
        """
        policy = self._by_agent.get(agent)
        if policy is None:
            return PolicyDecision(True, "no_policy")
        if policy.allow_tools is None:
            return PolicyDecision(True, "no_tool_rules")
        if tool_name in policy.allow_tools:
            return PolicyDecision(True, f"allow_tools:{tool_name}")
        return PolicyDecision(False, f"deny:tool:{tool_name}")

    def filter_memory_agents(self, agent: str) -> set[str] | None:
        """Return allowed agent names for memory read, or ``None`` (no restriction).

        The keyword ``"shared"`` in the returned set matches memories with
        ``type=MemoryType.SHARED``. All other entries are literal agent names.

        Args:
            agent: Name of the agent whose memory-read scope is being queried.

        Returns:
            A set of allowed agent names (may include ``"shared"``), or
            ``None`` when no memory restriction applies.
        """
        policy = self._by_agent.get(agent)
        if policy is None or policy.allow_memory_read is None:
            return None
        return set(policy.allow_memory_read)

    def has_policy(self, agent: str) -> bool:
        """Check whether an agent has any policy entry.

        Args:
            agent: Name of the agent to look up.

        Returns:
            ``True`` if a policy exists for *agent*, ``False`` otherwise.
        """
        return agent in self._by_agent
