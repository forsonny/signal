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
