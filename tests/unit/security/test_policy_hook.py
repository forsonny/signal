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
