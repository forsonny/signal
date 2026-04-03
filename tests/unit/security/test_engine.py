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
