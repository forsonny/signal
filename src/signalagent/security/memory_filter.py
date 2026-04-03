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
