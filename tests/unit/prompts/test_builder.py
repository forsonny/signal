"""Unit tests for build_system_prompt -- pure function, no mocking needed."""
from datetime import datetime, timezone
from unittest.mock import patch

from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT


def _make_memory(
    content: str = "Test memory content",
    memory_type: MemoryType = MemoryType.LEARNING,
    tags: list[str] | None = None,
) -> Memory:
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001",
        agent="test-agent",
        type=memory_type,
        tags=tags if tags is not None else ["test"],
        content=content,
        confidence=0.8,
        version=1,
        created=now,
        updated=now,
        accessed=now,
        access_count=0,
    )


def _stub_count_tokens(text: str, model: str) -> int:
    """Approximate: 1 token per 4 characters."""
    return len(text) // 4


def _stub_context_window(model: str) -> int:
    """Return a realistic context window for testing."""
    return 10000


class TestBuildSystemPrompt:
    def test_identity_only_when_no_memories(self):
        """No memories -> returns identity unchanged."""
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            result = build_system_prompt("You are a test agent.", [], "test-model")
        assert result == "You are a test agent."
        assert "## Context" not in result

    def test_includes_memories_with_context_header(self):
        """Memories get included under a ## Context header."""
        mem = _make_memory(content="Important fact", tags=["python"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            result = build_system_prompt("You are a test agent.", [mem], "test-model")
        assert "## Context" in result
        assert "Important fact" in result
        assert "You are a test agent." in result

    def test_memory_format_with_tags(self):
        """Memory heading includes type and first tag."""
        mem = _make_memory(content="Some content", memory_type=MemoryType.PATTERN, tags=["refactoring", "python"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            result = build_system_prompt("Identity.", [mem], "test-model")
        assert "### pattern: refactoring" in result
        assert "Some content" in result

    def test_memory_format_without_tags(self):
        """Memory with empty tags uses type only as heading."""
        mem = _make_memory(content="No tag content", tags=[])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            result = build_system_prompt("Identity.", [mem], "test-model")
        assert "### learning" in result
        assert ": " not in result.split("### learning")[1].split("\n")[0]

    def test_budget_truncation_drops_excess_memories(self):
        """Memories that exceed budget are dropped (whole-memory truncation)."""
        small_mem = _make_memory(content="short")
        big_mem = _make_memory(content="x" * 2000)  # ~500 tokens, won't fit
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=200):
            result = build_system_prompt("Id.", [small_mem, big_mem], "test-model",
                                         response_reserve=50)
        assert "short" in result
        assert "x" * 2000 not in result

    def test_no_budget_returns_identity_only(self):
        """When response_reserve exceeds context window, return identity only."""
        mem = _make_memory(content="Should not appear")
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=100):
            result = build_system_prompt("A" * 400, [mem], "test-model",
                                         response_reserve=100)
        assert result == "A" * 400
        assert "Should not appear" not in result

    def test_identity_comes_first(self):
        """Identity text appears before context section."""
        mem = _make_memory(content="Memory text")
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            result = build_system_prompt("Identity first.", [mem], "test-model")
        identity_pos = result.index("Identity first.")
        context_pos = result.index("## Context")
        assert identity_pos < context_pos

    def test_multiple_memories_in_order(self):
        """Memories are included in the order provided (score order from engine)."""
        mem1 = _make_memory(content="First memory", tags=["a"])
        mem2 = _make_memory(content="Second memory", tags=["b"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=2000):
            result = build_system_prompt("Id.", [mem1, mem2], "test-model")
        pos1 = result.index("First memory")
        pos2 = result.index("Second memory")
        assert pos1 < pos2

    def test_default_memory_limit_is_defined(self):
        """DEFAULT_MEMORY_LIMIT exists and is a positive integer."""
        assert isinstance(DEFAULT_MEMORY_LIMIT, int)
        assert DEFAULT_MEMORY_LIMIT > 0
