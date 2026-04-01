"""Bootstrap -- single wiring point for the multi-agent runtime."""
from __future__ import annotations
from pathlib import Path

from signalagent.agents.host import AgentHost
from signalagent.agents.micro import MicroAgent
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AILayer
from signalagent.comms.bus import MessageBus
from signalagent.core.config import SignalConfig
from signalagent.core.models import Profile, ToolResult
from signalagent.runtime.executor import Executor
from signalagent.runtime.runner import AgenticRunner
from signalagent.tools.builtins import load_builtin_tool
from signalagent.tools.registry import ToolRegistry


async def bootstrap(
    instance_dir: Path,
    config: SignalConfig,
    profile: Profile,
) -> tuple[Executor, MessageBus, AgentHost]:
    """Wire up the full multi-agent runtime."""
    ai = AILayer(config)
    bus = MessageBus()
    host = AgentHost(bus)

    # Tool registry
    registry = ToolRegistry()
    for tool_name in profile.plugins.available:
        tool = load_builtin_tool(tool_name, instance_dir)
        if tool is not None:
            registry.register(tool)

    # Tool executor -- thin wrapper, 4b replaces with hook-aware version
    async def tool_executor(tool_name: str, arguments: dict) -> ToolResult:
        tool = registry.get(tool_name)
        if tool is None:
            return ToolResult(output="", error=f"Unknown tool: {tool_name}")
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    global_max = config.tools.max_iterations

    # Prime agent (no tools)
    prime = PrimeAgent(identity=profile.prime.identity, ai=ai, host=host, bus=bus)
    host.register(prime, talks_to=None)

    # Micro-agents with runners
    for micro_config in profile.micro_agents:
        agent_max = min(micro_config.max_iterations, global_max)
        tool_schemas = registry.get_schemas(micro_config.plugins)
        runner = AgenticRunner(
            ai=ai, tool_executor=tool_executor,
            tool_schemas=tool_schemas, max_iterations=agent_max,
        )
        agent = MicroAgent(config=micro_config, runner=runner)
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)

    executor = Executor(bus=bus)
    return executor, bus, host
