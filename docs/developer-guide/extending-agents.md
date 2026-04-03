# Extending Agents

## What you'll learn

- How to add a new micro-agent via profile YAML
- How Prime routes tasks to micro-agents using LLM classification
- When and how to write a custom `MicroAgent` subclass
- How to test your custom agent
- A complete working example

---

## How micro-agents work

A micro-agent is a specialist in the Signal runtime. Prime receives every
user message and decides which micro-agent should handle it based on the
agent's `name` and `skill` description. Each micro-agent gets its own
agentic loop (LLM + tool calling) bounded by `max_iterations`.

Adding a micro-agent requires no Python code in the common case -- you
define it in the profile YAML and Signal wires everything at bootstrap.

---

## Adding a micro-agent via profile YAML

### 1. Add the entry to your profile

Open your instance's profile YAML (or create a custom one). Add an entry
to the `micro_agents` list:

```yaml
micro_agents:
  - name: researcher
    skill: "Search the web, summarize findings, and cite sources"
    plugins:
      - file_system
    talks_to: []
    max_iterations: 15
```

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Unique agent name. Used for routing and memory scoping. |
| `skill` | `str` | Yes | One-line description of what this agent does. Prime uses this for routing decisions. |
| `plugins` | `list[str]` | No | Tool plugin names this agent can use (default: `[]`). |
| `talks_to` | `list[str]` | No | Agent names this agent can send messages to (default: `[]`). |
| `can_spawn_subs` | `bool` | No | Whether this agent can spawn sub-agents (default: `false`). |
| `max_iterations` | `int` | No | Max agentic loop iterations (default: `10`, min: `1`). Capped by global `tools.max_iterations`. |
| `mcp_servers` | `list[str]` | No | MCP server names (default: `[]`). |
| `scripts` | `list[str]` | No | Script paths (default: `[]`). |

### 2. Make tools available

If your agent needs tools, list them in both `plugins.available` (global
tool loading) and the agent's `plugins` field (per-agent access):

```yaml
plugins:
  available:
    - file_system

micro_agents:
  - name: researcher
    skill: "Search the web, summarize findings, and cite sources"
    plugins:
      - file_system
```

Tools listed in `plugins.available` are loaded at bootstrap.
Tools listed in the agent's `plugins` are the subset that agent can use.

### 3. How Prime routing works

When Prime receives a user message, it makes an LLM call with a prompt like:

```
You are a routing agent. Given the user's message and the
available specialist agents below, decide which agent should
handle this task.

Available agents (2):
- coder: Write and debug Python code
- researcher: Search the web, summarize findings, and cite sources

If none of the agents are a good fit, respond with: NONE

Otherwise respond with exactly the agent name, nothing else.

User message: Find recent papers on transformer architectures
```

The LLM responds with the agent name (case-insensitive match). If it
returns `NONE`, an unrecognized name, or the call fails, Prime handles
the request directly.

Write your `skill` field to be a clear, specific description of what the
agent does. This is the primary input to the routing decision.

---

## Custom MicroAgent subclass

In most cases, the standard `MicroAgent` is sufficient. You need a
subclass only when you need to:

- Override identity prompt construction
- Add pre/post-processing around the runner
- Inject custom state or dependencies

### When to subclass

| Scenario | Use standard `MicroAgent` | Subclass |
|---|---|---|
| Different skill description | Yes | No |
| Different tools | Yes | No |
| Custom system prompt format | No | Yes |
| Pre-processing before runner | No | Yes |
| Custom memory retrieval logic | No | Yes |

### Subclass example

```python
"""Custom agent with domain-specific prompt formatting."""
from __future__ import annotations

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import (
    MemoryReaderProtocol,
    RunnerProtocol,
    WorktreeProxyProtocol,
)


class CodeReviewAgent(MicroAgent):
    """Agent that formats its identity with a code review checklist."""

    def __init__(
        self,
        config: MicroAgentConfig,
        runner: RunnerProtocol,
        memory_reader: MemoryReaderProtocol | None = None,
        model: str = "",
        worktree_proxy: WorktreeProxyProtocol | None = None,
    ) -> None:
        super().__init__(
            config=config, runner=runner,
            memory_reader=memory_reader, model=model,
            worktree_proxy=worktree_proxy,
        )

    def _build_identity(self) -> str:
        """Override to include a structured review checklist."""
        return (
            f"You are {self._config.name}, a code review specialist "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "Review checklist:\n"
            "1. Correctness: Does the code do what it claims?\n"
            "2. Error handling: Are edge cases covered?\n"
            "3. Performance: Any obvious bottlenecks?\n"
            "4. Style: Does it match the project conventions?\n\n"
            "Complete the review and return your findings."
        )
```

### Registration

Custom subclasses are not auto-discovered from YAML. You need to
instantiate them in bootstrap or write a custom bootstrap extension.
For standard `MicroAgent` usage via YAML, no registration code is
needed -- `bootstrap()` handles it.

---

## Testing your agent

### Test routing

Verify that Prime routes to your agent based on the skill description:

```python
from unittest.mock import AsyncMock
from signalagent.ai.layer import AIResponse
from signalagent.agents.prime import PrimeAgent
from signalagent.agents.host import AgentHost
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT


def _make_response(content: str) -> AIResponse:
    return AIResponse(
        content=content, model="test", provider="test",
        input_tokens=10, output_tokens=20, tool_calls=[],
    )


class TestResearcherRouting:
    @pytest.mark.asyncio
    async def test_routes_to_researcher(self):
        mock_ai = AsyncMock()
        bus = MessageBus()
        host = AgentHost(bus)

        prime = PrimeAgent(
            identity="You are helpful.",
            ai=mock_ai, host=host, bus=bus,
        )
        host.register(prime, talks_to=None)

        # Register a mock micro-agent
        mock_micro = AsyncMock()
        mock_micro.name = "researcher"
        mock_micro.agent_type = AgentType.MICRO
        mock_micro.skill = "Search the web and summarize findings"
        mock_micro.status = AgentStatus.CREATED
        mock_micro.handle = AsyncMock(return_value=Message(
            type=MessageType.RESULT, sender="researcher",
            recipient=PRIME_AGENT, content="Found 3 papers",
        ))
        host.register(mock_micro, talks_to=set())

        # Routing call returns "researcher"
        mock_ai.complete = AsyncMock(side_effect=[
            _make_response("researcher"),
        ])

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="Find papers on transformers",
        )
        result = await prime.handle(msg)
        assert result.content == "Found 3 papers"
```

### Test the agent directly

```python
from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import MessageType
from signalagent.runtime.runner import RunnerResult


class TestResearcherAgent:
    @pytest.mark.asyncio
    async def test_handles_task(self):
        config = MicroAgentConfig(
            name="researcher",
            skill="Search the web and summarize findings",
        )
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=RunnerResult(
            content="Found 3 papers on transformers.",
            iterations=2, tool_calls_made=1,
        ))

        agent = MicroAgent(config=config, runner=mock_runner)

        msg = Message(
            type=MessageType.TASK, sender="prime",
            recipient="researcher", content="Find papers",
        )
        result = await agent.handle(msg)
        assert "3 papers" in result.content
```

---

## Complete example

### Profile YAML

```yaml
name: research-team
description: "A research-focused agent team"
version: "1.0.0"

prime:
  identity: >
    You are a research coordinator. Route tasks to the
    appropriate specialist agent.

micro_agents:
  - name: researcher
    skill: "Search the web, summarize findings, and cite sources"
    plugins:
      - file_system
    max_iterations: 15

  - name: writer
    skill: "Write polished reports and documentation from research notes"
    plugins:
      - file_system
    talks_to:
      - researcher
    max_iterations: 10

plugins:
  available:
    - file_system

hooks:
  active:
    - log_tool_calls
```

### Usage

```bash
signal init --profile research-team
signal talk "Find recent papers on transformer architectures"
```

Prime routes to `researcher`. The researcher uses the agentic loop with
`file_system` tools, completes the task, and returns the result through
the bus.

---

## Next steps

- [Architecture](architecture.md) -- how agents fit into the runtime
- [Extending Tools](extending-tools.md) -- giving agents new capabilities
- [Extending Hooks](extending-hooks.md) -- observing and controlling agent behavior
- [Testing](testing.md) -- test patterns for agents
