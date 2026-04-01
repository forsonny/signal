# Phase 4c: Sub-Agent Spawning -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow micro-agents with `can_spawn_subs: True` to spawn ephemeral sub-agents via a `spawn_sub_agent` tool call. Sub-agents inherit the parent's tools (minus spawn), execute with their own agentic loop, and return results as a normal `ToolResult`.

**Architecture:** `SpawnSubAgentTool` implements the standard `Tool` protocol. An injected runner factory callable (`run_sub`) creates ephemeral `AgenticRunner` instances -- the tool has no `runtime/` dependency. Bootstrap creates per-agent executors for spawning agents that intercept `spawn_sub_agent` calls and delegate everything else to the shared executor.

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, pytest with asyncio_mode="auto"

---

### Task 1: SpawnSubAgentTool

**Files:**
- Create: `src/signalagent/tools/builtins/spawn_sub_agent.py`
- Create: `tests/unit/tools/builtins/test_spawn_sub_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/tools/builtins/test_spawn_sub_agent.py
"""Unit tests for SpawnSubAgentTool -- mock runner factory."""

import pytest
from unittest.mock import AsyncMock

from signalagent.tools.builtins.spawn_sub_agent import SpawnSubAgentTool


@pytest.fixture
def mock_run_sub():
    return AsyncMock(return_value="Sub-agent completed the analysis.")


@pytest.fixture
def tool(mock_run_sub):
    return SpawnSubAgentTool(run_sub=mock_run_sub, parent_name="researcher")


class TestSpawnSubAgentToolProperties:
    def test_name(self, tool):
        assert tool.name == "spawn_sub_agent"

    def test_description_is_nonempty(self, tool):
        assert len(tool.description) > 0

    def test_parameters_schema(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "task" in params["properties"]
        assert "skill" in params["properties"]
        assert set(params["required"]) == {"task", "skill"}


class TestSpawnSubAgentExecution:
    @pytest.mark.asyncio
    async def test_calls_run_sub_with_system_prompt_and_task(self, tool, mock_run_sub):
        result = await tool.execute(task="Analyze the logs", skill="Log analysis")
        mock_run_sub.assert_called_once()
        call_args = mock_run_sub.call_args[0]
        system_prompt, task = call_args
        assert "sub_researcher_1" in system_prompt
        assert "Log analysis" in system_prompt
        assert task == "Analyze the logs"

    @pytest.mark.asyncio
    async def test_returns_tool_result_with_output(self, tool):
        result = await tool.execute(task="Do something", skill="General")
        assert result.output == "Sub-agent completed the analysis."
        assert result.error is None

    @pytest.mark.asyncio
    async def test_auto_generates_sequential_names(self, tool, mock_run_sub):
        await tool.execute(task="Task 1", skill="Skill A")
        await tool.execute(task="Task 2", skill="Skill B")
        first_prompt = mock_run_sub.call_args_list[0][0][0]
        second_prompt = mock_run_sub.call_args_list[1][0][0]
        assert "sub_researcher_1" in first_prompt
        assert "sub_researcher_2" in second_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_contains_skill(self, tool, mock_run_sub):
        await tool.execute(task="Review code", skill="Code quality")
        system_prompt = mock_run_sub.call_args[0][0]
        assert "Code quality" in system_prompt
        assert "ephemeral sub-agent" in system_prompt

    @pytest.mark.asyncio
    async def test_run_sub_error_propagates(self, mock_run_sub):
        mock_run_sub.side_effect = Exception("Runner failed")
        tool = SpawnSubAgentTool(run_sub=mock_run_sub, parent_name="test")
        with pytest.raises(Exception, match="Runner failed"):
            await tool.execute(task="Fail", skill="Testing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/builtins/test_spawn_sub_agent.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.tools.builtins.spawn_sub_agent'`

- [ ] **Step 3: Implement SpawnSubAgentTool**

```python
# src/signalagent/tools/builtins/spawn_sub_agent.py
"""SpawnSubAgentTool -- spawns ephemeral sub-agents for task delegation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from signalagent.core.models import ToolResult


class SpawnSubAgentTool:
    """Spawns an ephemeral sub-agent to handle a subtask.

    The sub-agent gets its own agentic loop (via the injected run_sub
    callable) with the parent's tools minus this spawn tool. The result
    is returned as a normal ToolResult.

    Implements the Tool protocol. The runner, hooks, and registry
    don't know this tool is special.
    """

    def __init__(
        self,
        run_sub: Callable[[str, str], Awaitable[str]],
        parent_name: str,
    ) -> None:
        self._run_sub = run_sub
        self._parent_name = parent_name
        self._counter = 0
        # NOTE: _counter as instance state works because tool calls
        # are sequential on a single coroutine (no concurrent spawns
        # in 4c).

    @property
    def name(self) -> str:
        return "spawn_sub_agent"

    @property
    def description(self) -> str:
        return "Spawn an ephemeral sub-agent to handle a subtask."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the sub-agent to complete.",
                },
                "skill": {
                    "type": "string",
                    "description": "The sub-agent's area of expertise.",
                },
            },
            "required": ["task", "skill"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Spawn a sub-agent, run it, return its result."""
        task = kwargs.get("task", "")
        skill = kwargs.get("skill", "")

        self._counter += 1
        sub_name = f"sub_{self._parent_name}_{self._counter}"

        system_prompt = (
            f"You are {sub_name}, an ephemeral sub-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {skill}\n\n"
            "Complete the task and return your results."
        )

        result_text = await self._run_sub(system_prompt, task)
        return ToolResult(output=result_text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/tools/builtins/test_spawn_sub_agent.py -v`
Expected: All PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/tools/builtins/spawn_sub_agent.py tests/unit/tools/builtins/test_spawn_sub_agent.py
git commit -m "feat: add SpawnSubAgentTool for ephemeral sub-agent delegation"
```

---

### Task 2: Wire sub-agent spawning in bootstrap and add integration tests

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Update bootstrap.py**

Replace the micro-agent wiring section (lines 65-75) of `src/signalagent/runtime/bootstrap.py`. Add the import at the top:

```python
from signalagent.tools.builtins.spawn_sub_agent import SpawnSubAgentTool
```

Replace the micro-agent loop (the `# Micro-agents with runners` section through the end of the loop):

```python
    # Micro-agents with runners
    for micro_config in profile.micro_agents:
        agent_max = min(micro_config.max_iterations, global_max)
        tool_schemas = registry.get_schemas(micro_config.plugins)

        if micro_config.can_spawn_subs:
            # Sub-agent runner factory: uses parent's tools (no spawn)
            async def run_sub(
                system_prompt: str, task: str,
                _schemas=tool_schemas, _max=agent_max,
            ) -> str:
                sub_runner = AgenticRunner(
                    ai=ai, tool_executor=tool_executor,
                    tool_schemas=_schemas, max_iterations=_max,
                )
                result = await sub_runner.run(
                    system_prompt=system_prompt, user_content=task,
                )
                return result.content

            # Create spawn tool
            spawn_tool = SpawnSubAgentTool(
                run_sub=run_sub, parent_name=micro_config.name,
            )

            # Per-agent executor: intercepts spawn, delegates rest to shared
            async def agent_inner(
                tool_name: str, arguments: dict,
                _spawn=spawn_tool, _shared=inner_executor,
            ) -> ToolResult:
                if tool_name == _spawn.name:
                    return await _spawn.execute(**arguments)
                return await _shared(tool_name, arguments)

            # Wrap with hooks
            agent_executor = HookExecutor(
                inner=agent_inner, registry=hook_registry,
            )

            # Append spawn schema to full list
            full_schemas = list(tool_schemas)
            full_schemas.append({
                "type": "function",
                "function": {
                    "name": spawn_tool.name,
                    "description": spawn_tool.description,
                    "parameters": spawn_tool.parameters,
                },
            })

            runner = AgenticRunner(
                ai=ai, tool_executor=agent_executor,
                tool_schemas=full_schemas, max_iterations=agent_max,
            )
        else:
            # No spawn capability -- use shared executor
            runner = AgenticRunner(
                ai=ai, tool_executor=tool_executor,
                tool_schemas=tool_schemas, max_iterations=agent_max,
            )

        agent = MicroAgent(config=micro_config, runner=runner)
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)
```

- [ ] **Step 2: Add bootstrap test fixtures and tests**

Add the following to `tests/unit/runtime/test_bootstrap.py`.

New fixtures (after `profile_with_hooks`):

```python
@pytest.fixture
def profile_with_spawn():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="manager", skill="Task management",
                talks_to=["prime"], plugins=["file_system"],
                can_spawn_subs=True,
            ),
        ],
    )


@pytest.fixture
def profile_without_spawn():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="worker", skill="Basic work",
                talks_to=["prime"], plugins=["file_system"],
                can_spawn_subs=False,
            ),
        ],
    )
```

New tests in `TestBootstrap` class:

```python
    @pytest.mark.asyncio
    async def test_sub_agent_spawn_end_to_end(self, tmp_path, config, profile_with_spawn, monkeypatch):
        """Micro-agent spawns sub-agent, sub-agent uses tool, result flows back."""
        (tmp_path / "data.txt").write_text("secret info")

        # Tool calls: parent spawns sub-agent, sub-agent reads file
        spawn_tc = ToolCallRequest(
            id="call_1", name="spawn_sub_agent",
            arguments={"task": "Read data.txt and summarize", "skill": "File analysis"},
        )
        file_tc = ToolCallRequest(
            id="call_2", name="file_system",
            arguments={"operation": "read", "path": "data.txt"},
        )

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            # Prime routes to manager
            _make_ai_response("manager"),
            # Manager's runner: LLM calls spawn_sub_agent
            _make_ai_response("", tool_calls=[spawn_tc]),
            # Sub-agent's runner: LLM calls file_system
            _make_ai_response("", tool_calls=[file_tc]),
            # Sub-agent's runner: LLM returns final text
            _make_ai_response("File contains: secret info"),
            # Manager's runner: LLM returns final text (after getting spawn result)
            _make_ai_response("Sub-agent found: secret info"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_spawn)
        result = await executor.run("analyze data.txt")

        assert result.content == "Sub-agent found: secret info"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_spawn_without_can_spawn_subs(self, tmp_path, config, profile_without_spawn, monkeypatch):
        """Micro-agent without can_spawn_subs does NOT get spawn_sub_agent tool."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("worker"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_without_spawn)

        # Verify the worker's AI call did NOT receive spawn_sub_agent in tools
        await executor.run("do something")
        # The second call is the worker's runner call
        worker_call = mock_ai.complete.call_args_list[1]
        tools = worker_call.kwargs.get("tools") or []
        tool_names = [t["function"]["name"] for t in tools]
        assert "spawn_sub_agent" not in tool_names
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat: wire sub-agent spawning in bootstrap with per-agent executors"
```

---

### Task 3: Update docs, bump version, verify end-to-end

**Files:**
- Modify: `docs/dev/architecture.md`
- Modify: `docs/dev/project-structure.md`
- Modify: `docs/dev/testing.md`
- Modify: `docs/dev/roadmap.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Modify: `src/signalagent/__init__.py`

- [ ] **Step 1: Run full test suite and count**

Run: `uv run pytest -x -q`
Expected: All pass. Note test count.

- [ ] **Step 2: Update architecture.md**

- Update header to "Phase 4c"
- Add a "Sub-Agent Spawning" subsection:
  - `spawn_sub_agent` is a tool call, not a new mechanism
  - Ephemeral lifecycle: spawn, execute, return, destroy
  - Sub-agents inherit parent's tools minus spawn (no recursion)
  - Per-agent executor intercepts spawn calls, shared executor handles regular tools
  - Sub-agent tool calls are fully hooked

- [ ] **Step 3: Update project-structure.md**

Add:
- `tools/builtins/spawn_sub_agent.py` -- SpawnSubAgentTool
- Test file entry

- [ ] **Step 4: Update roadmap.md**

Add Phase 4c row: Sub-Agent Spawning -- Complete

- [ ] **Step 5: Update testing.md**

Update test count. Add sub-agent test pattern note (mock runner factory, end-to-end spawn test).

- [ ] **Step 6: Update README.md**

Update status to "Phase 4c of 10 complete." Add sub-agent description.

- [ ] **Step 7: Update CHANGELOG.md**

Add `## [0.6.0] - 2026-03-31` section:
### Added
- SpawnSubAgentTool for ephemeral sub-agent delegation via tool calls
- Per-agent executor pipeline for micro-agents with can_spawn_subs
- Sub-agents inherit parent's tools minus spawn (no recursion)
### Changed
- Bootstrap creates per-agent executors for spawning agents

- [ ] **Step 8: Bump version**

`src/signalagent/__init__.py`: `__version__ = "0.6.0"`
`VERSION`: `0.6.0`

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -v`
Expected: All pass

- [ ] **Step 10: Commit**

```bash
git add docs/ README.md CHANGELOG.md
git commit -m "docs: update architecture, structure, testing, and roadmap for Phase 4c"

git add VERSION src/signalagent/__init__.py
git commit -m "chore: bump version to 0.6.0 for Phase 4c sub-agent spawning"
```

---

## Self-Review

**Spec coverage check:**
- (a) SpawnSubAgentTool with Tool protocol, task + skill params: Task 1
- (b) Spawning is a tool call, result feeds back to parent loop: Task 1, Task 2
- (c) Sub-agent via injected runner factory, no runtime/ dependency in tools/: Task 1
- (d) Parent's tools minus spawn, no recursion: Task 2 (bootstrap wiring)
- (e) Ephemeral, no persistent registration: Task 1 (tool creates and discards runner)
- (f) Only can_spawn_subs: True gets spawn tool: Task 2 (bootstrap if/else)
- (g) Per-agent executor intercepts spawn, hooks observe: Task 2 (agent_inner + HookExecutor)
- (h) Sub-agent tool calls through same HookExecutor: Task 2 (run_sub uses tool_executor)
- (i) Auto-generated name sub_{parent}_{counter}: Task 1
- (j) End-to-end: Task 2 (test_sub_agent_spawn_end_to_end)
- (k) Negative test -- no spawn without can_spawn_subs: Task 2 (test_no_spawn_without_can_spawn_subs)

All 11 done-when criteria covered.

**Placeholder scan:** No TBD, TODO, or vague steps found.

**Type consistency check:**
- `SpawnSubAgentTool(run_sub=, parent_name=)` consistent between Task 1 (implementation) and Task 2 (bootstrap)
- `run_sub: Callable[[str, str], Awaitable[str]]` consistent between Task 1 (constructor type) and Task 2 (bootstrap closure)
- `spawn_tool.name` used in agent_inner (not hardcoded "spawn_sub_agent")
- `tool_schemas` (without spawn) passed to run_sub closure, `full_schemas` (with spawn) passed to parent's runner -- consistent with spec
- `ToolResult` return type consistent across execute() and agent_inner
