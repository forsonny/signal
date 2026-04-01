# Phase 4c: Sub-Agent Spawning -- Design Spec

## Goal

Allow micro-agents to spawn ephemeral sub-agents for task delegation. Sub-agent spawning is a tool call -- the LLM calls `spawn_sub_agent` like any other tool, a temporary agent executes the task, and the result feeds back into the parent's agentic loop. No new protocols, no new packages -- just a new built-in tool.

## Architecture

Phase 4c adds one new file and modifies one existing module:

**New:**
- `tools/builtins/spawn_sub_agent.py` -- `SpawnSubAgentTool` implementing the `Tool` protocol

**Modified:**
- `runtime/bootstrap.py` -- per-agent wiring for micro-agents with `can_spawn_subs: True`
- `tools/builtins/__init__.py` -- no change needed (spawn tool is not loaded via `load_builtin_tool`, it's constructed per-agent at bootstrap)

### Flow

```
MicroAgent (can_spawn_subs=True)
  |
  AgenticRunner loop
  |
  LLM returns tool_call: spawn_sub_agent(task="...", skill="...")
  |
  HookExecutor (hooks see spawn as a normal tool call)
  |
  Per-agent executor -> SpawnSubAgentTool.execute()
  |
  SpawnSubAgentTool calls run_sub(system_prompt, task):
    - Bootstrap-provided closure creates ephemeral AgenticRunner
    - Runner has parent's tools (minus spawn), parent's executor, capped iterations
    - Runner executes: LLM calls, tool calls, iteration loop
    - Returns result text
  |
  ToolResult(output=result_text) fed back to parent's loop
  |
  Parent continues or returns final answer
```

Sub-agent tool calls go through the same `tool_executor` (HookExecutor) as the parent's calls -- fully hooked, fully logged.

### Dependency Graph

```
tools/builtins/spawn_sub_agent.py --> core/models (ToolResult) only
runtime/bootstrap.py              --> tools/builtins/spawn_sub_agent, runtime/runner
```

`tools/` has no dependency on `runtime/`. The runner factory is injected via a callable at bootstrap.

---

## Components

### 1. SpawnSubAgentTool (tools/builtins/spawn_sub_agent.py)

Implements the standard `Tool` protocol:

```python
class SpawnSubAgentTool:
    def __init__(
        self,
        run_sub: Callable[[str, str], Awaitable[str]],
        parent_name: str,
    ) -> None:
        self._run_sub = run_sub
        self._parent_name = parent_name
        self._counter = 0
        # NOTE: _counter as instance state works because tool calls are
        # sequential on a single coroutine (no concurrent spawns in 4c).

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

**Key properties:**
- `run_sub` is an injected callable `(system_prompt: str, task: str) -> str` provided by bootstrap. The tool never imports or knows about AgenticRunner.
- `parent_name` is used to generate the sub-agent name for logging/debugging.
- Auto-generated name: `sub_{parent}_{counter}` (e.g., `sub_researcher_1`).
- Implements `Tool` protocol -- the runner, hooks, and registry don't know it's special.

### 2. Bootstrap Wiring (runtime/bootstrap.py)

For micro-agents with `can_spawn_subs: True`, bootstrap creates a per-agent executor pipeline:

```python
for micro_config in profile.micro_agents:
    agent_max = min(micro_config.max_iterations, global_max)
    tool_schemas = registry.get_schemas(micro_config.plugins)

    if micro_config.can_spawn_subs:
        # 1. Create runner factory for sub-agents (uses parent's tools, no spawn)
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

        # 2. Create spawn tool
        spawn_tool = SpawnSubAgentTool(
            run_sub=run_sub, parent_name=micro_config.name,
        )

        # 3. Per-agent executor: intercepts spawn, delegates rest to shared
        async def agent_inner(
            tool_name: str, arguments: dict,
            _spawn=spawn_tool, _shared=inner_executor,
        ) -> ToolResult:
            if tool_name == _spawn.name:
                return await _spawn.execute(**arguments)
            return await _shared(tool_name, arguments)

        # 4. Wrap with hooks
        agent_executor = HookExecutor(inner=agent_inner, registry=hook_registry)

        # 5. Append spawn schema to full list
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

**Key details:**
- Default keyword arguments (`_schemas=tool_schemas`, `_spawn=spawn_tool`, `_shared=inner_executor`) capture loop variables correctly in closures.
- Sub-agent's `tool_schemas` is the parent's regular schemas (no spawn) -- prevents recursion.
- Sub-agent's `tool_executor` is the shared `tool_executor` (HookExecutor wrapping inner_executor) -- sub-agent tool calls are hooked.
- Per-agent executor uses `spawn_tool.name` (not hardcoded string) for the intercept check.
- Agents without `can_spawn_subs` use the shared executor unchanged -- zero overhead.

### 3. Sub-Agent Lifecycle

1. **Spawn:** Parent LLM calls `spawn_sub_agent(task, skill)`. HookExecutor runs before hooks (can block spawn). Per-agent executor routes to `SpawnSubAgentTool.execute()`.

2. **Execute:** The tool calls `run_sub(system_prompt, task)`. Bootstrap's closure creates an ephemeral `AgenticRunner` and runs it. The sub-agent's LLM makes its own AI calls, uses parent's tools (through the shared HookExecutor), iterates until done or limit hit.

3. **Return:** `RunnerResult.content` becomes `ToolResult.output`. HookExecutor runs after hooks (log_tool_calls logs the spawn). Parent's loop receives the result as a normal tool result and continues.

4. **Destroy:** The ephemeral `AgenticRunner` goes out of scope. No registration on the bus, no entry in AgentHost, no cleanup needed. Garbage collected.

### 4. What Sub-Agents Cannot Do

- **Cannot spawn sub-agents:** Their tool schemas don't include `spawn_sub_agent`.
- **Cannot exceed parent's tools:** They inherit exactly the parent's regular tool set.
- **Cannot exceed parent's iteration limit:** Same `agent_max` cap.
- **Cannot send bus messages:** They're not registered on the bus. They only interact through tools.
- **Cannot persist state:** No registration, no memory access, no session state.

---

## Error Handling

- **Sub-agent LLM fails:** The AgenticRunner's own error handling applies. The runner catches AI errors and returns what it has.
- **Sub-agent hits iteration limit:** `RunnerResult.truncated = True`. The spawn tool returns whatever content the sub-agent produced.
- **Sub-agent tool call fails:** The sub-agent's runner handles it (feeds error back to sub-agent's LLM). The parent never sees internal sub-agent failures -- only the final result.
- **Spawn blocked by hook:** Before hook returns `ToolResult` with error. Parent's LLM sees "Blocked: {reason}" and can decide what to do.
- **SpawnSubAgentTool.execute() raises:** The parent's runner catches it (same error handling as any tool), feeds error back to parent's LLM.

---

## File Layout

```
src/signalagent/
  tools/
    builtins/
      spawn_sub_agent.py  -- NEW: SpawnSubAgentTool

  runtime/
    bootstrap.py          -- MODIFIED: per-agent wiring for can_spawn_subs

tests/
  unit/
    tools/
      builtins/
        test_spawn_sub_agent.py -- NEW: SpawnSubAgentTool tests
    runtime/
      test_bootstrap.py         -- MODIFIED: add spawn tests
```

---

## Done-When Criteria

**(a)** `SpawnSubAgentTool` implements the `Tool` protocol with `task` and `skill` parameters

**(b)** Spawning is a tool call -- the LLM calls `spawn_sub_agent` like any other tool, result feeds back into the parent's agentic loop

**(c)** Sub-agent gets its own `AgenticRunner` via injected runner factory -- `tools/` has no `runtime/` dependency

**(d)** Sub-agent inherits parent's tools minus `spawn_sub_agent` -- no recursion, no privilege escalation

**(e)** Sub-agent is ephemeral -- created, executed, result returned, no persistent registration

**(f)** Only micro-agents with `can_spawn_subs: True` get the spawn tool

**(g)** Per-agent executor intercepts spawn calls, delegates everything else to shared executor, wrapped in HookExecutor -- hooks observe spawn calls

**(h)** Sub-agent's own tool calls go through the same HookExecutor -- fully hooked

**(i)** Auto-generated sub-agent name (`sub_{parent}_{counter}`) for logging

**(j)** `signal talk` works end-to-end: micro-agent spawns sub-agent, sub-agent uses tool, result flows back to parent, parent returns to user

**(k)** Micro-agents without `can_spawn_subs: True` do NOT get the spawn tool -- verified by explicit negative test
