"""Unit tests for MicroAgent -- mock runner only."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Memory, Message
from signalagent.core.types import AgentType, MemoryType, MessageType
from signalagent.runtime.runner import RunnerResult
from signalagent.worktrees.models import WorktreeResult

from datetime import datetime, timezone


def _make_config(name="code-review", skill="Code quality, security, style consistency"):
    return MicroAgentConfig(name=name, skill=skill)

def _make_runner_result(content="Review complete."):
    return RunnerResult(content=content, iterations=1, tool_calls_made=0)

def _make_task_message(content="Review this code"):
    return Message(id="msg_test0001", type=MessageType.TASK,
                   sender="prime", recipient="code-review", content=content)

def _make_memory(content="Relevant context", tags=None):
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001", agent="code-review", type=MemoryType.LEARNING,
        tags=tags or ["code"], content=content, confidence=0.8, version=1,
        created=now, updated=now, accessed=now, access_count=0,
    )


def _stub_count_tokens(text: str, model: str) -> int:
    """Approximate: 1 token per 4 characters."""
    return len(text) // 4


class TestMicroAgentConstruction:
    def test_name_from_config(self):
        agent = MicroAgent(config=_make_config(name="git-agent"), runner=AsyncMock())
        assert agent.name == "git-agent"
        assert agent.agent_type == AgentType.MICRO

    def test_skill_property_returns_config_skill(self):
        agent = MicroAgent(config=_make_config(skill="Code quality"), runner=AsyncMock())
        assert agent.skill == "Code quality"

    def test_identity_contains_name_and_skill(self):
        agent = MicroAgent(config=_make_config(name="code-review", skill="Code quality"), runner=AsyncMock())
        identity = agent._build_identity()
        assert "code-review" in identity
        assert "Code quality" in identity
        assert "specialist micro-agent" in identity


class TestMicroAgentExecution:
    @pytest.mark.asyncio
    async def test_delegates_to_runner(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        await agent._handle(_make_task_message())
        mock_runner.run.assert_called_once()
        call_kwargs = mock_runner.run.call_args.kwargs
        assert "code-review" in call_kwargs["system_prompt"]
        assert call_kwargs["user_content"] == "Review this code"

    @pytest.mark.asyncio
    async def test_returns_result_message(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result("All good."))
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        result = await agent._handle(_make_task_message())
        assert result is not None
        assert result.type == MessageType.RESULT
        assert result.content == "All good."
        assert result.sender == "code-review"
        assert result.recipient == "prime"
        assert result.parent_id == "msg_test0001"

    @pytest.mark.asyncio
    async def test_runner_error_propagates(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=Exception("LLM down"))
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        with pytest.raises(Exception, match="LLM down"):
            await agent._handle(_make_task_message())


class TestMicroAgentMemoryIntegration:
    @pytest.mark.asyncio
    async def test_retrieves_memories_and_enriches_prompt(self):
        """When memory_reader is provided, system prompt includes memories."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            await agent._handle(_make_task_message())

        mock_reader.search.assert_called_once()
        call_kwargs = mock_reader.search.call_args.kwargs
        assert call_kwargs["agent"] == "code-review"
        assert call_kwargs["limit"] == 20  # DEFAULT_MEMORY_LIMIT

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "Relevant context" in system_prompt
        assert "## Context" in system_prompt

    @pytest.mark.asyncio
    async def test_no_memory_reader_uses_identity_only(self):
        """Without memory_reader, prompt is the static identity string."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())

        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        await agent._handle(_make_task_message())

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "code-review" in system_prompt
        assert "## Context" not in system_prompt

    @pytest.mark.asyncio
    async def test_memory_search_failure_proceeds_without_context(self):
        """If memory search fails, agent proceeds with identity-only prompt."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(side_effect=Exception("DB error"))

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        result = await agent._handle(_make_task_message())

        assert result is not None
        assert result.content == "Review complete."
        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "## Context" not in system_prompt


class _FakeWorktreeProxy:
    """Minimal fake satisfying WorktreeProxyProtocol."""

    def __init__(self, result: WorktreeResult | None = None) -> None:
        self._result = result

    def take_result(self) -> WorktreeResult | None:
        r = self._result
        self._result = None
        return r


class TestMicroAgentWorktree:
    @pytest.mark.asyncio
    async def test_appends_review_instructions(self) -> None:
        wt_result = WorktreeResult(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["src/main.py", "src/utils.py"],
            diff="diff output",
            agent_name="coder",
            is_git=True,
        )
        proxy = _FakeWorktreeProxy(result=wt_result)
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Task complete.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix the bug",
        )
        response = await agent._handle(msg)
        assert "signal worktree merge wt_abc12345" in response.content
        assert "signal worktree discard wt_abc12345" in response.content
        assert "src/main.py" in response.content

    @pytest.mark.asyncio
    async def test_no_review_without_writes(self) -> None:
        proxy = _FakeWorktreeProxy(result=None)
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Analysis complete.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="analyzer", skill="analysis"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="analyzer", content="analyze this",
        )
        response = await agent._handle(msg)
        assert "worktree" not in response.content.lower()
        assert response.content == "Analysis complete."

    @pytest.mark.asyncio
    async def test_no_review_without_proxy(self) -> None:
        runner = AsyncMock()
        runner.run.return_value = MagicMock(content="Done.")

        agent = MicroAgent(
            config=MicroAgentConfig(name="basic", skill="general"),
            runner=runner,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="basic", content="do something",
        )
        response = await agent._handle(msg)
        assert response.content == "Done."

    @pytest.mark.asyncio
    async def test_preserves_worktree_on_runner_error(self) -> None:
        wt_result = WorktreeResult(
            id="wt_err12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["partial.py"],
            diff="partial diff",
            agent_name="coder",
            is_git=True,
        )
        proxy = _FakeWorktreeProxy(result=wt_result)
        runner = AsyncMock()
        runner.run.side_effect = RuntimeError("AI layer failed")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix it",
        )
        response = await agent._handle(msg)
        assert "signal worktree merge wt_err12345" in response.content
        assert "partial.py" in response.content
        assert "failed" in response.content.lower()

    @pytest.mark.asyncio
    async def test_reraises_without_worktree_state(self) -> None:
        proxy = _FakeWorktreeProxy(result=None)
        runner = AsyncMock()
        runner.run.side_effect = RuntimeError("AI layer failed")

        agent = MicroAgent(
            config=MicroAgentConfig(name="coder", skill="coding"),
            runner=runner,
            worktree_proxy=proxy,
        )
        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="coder", content="fix it",
        )
        with pytest.raises(RuntimeError, match="AI layer failed"):
            await agent._handle(msg)
