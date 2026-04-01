"""Bootstrap -- single wiring point for the multi-agent runtime."""

from __future__ import annotations

from pathlib import Path

from signalagent.agents.host import AgentHost
from signalagent.agents.micro import MicroAgent
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AILayer
from signalagent.comms.bus import MessageBus
from signalagent.core.config import SignalConfig
from signalagent.core.models import Profile
from signalagent.runtime.executor import Executor


async def bootstrap(
    instance_dir: Path,
    config: SignalConfig,
    profile: Profile,
) -> tuple[Executor, MessageBus, AgentHost]:
    """Wire up the full multi-agent runtime.

    1. Create AILayer from config
    2. Create MessageBus
    3. Create AgentHost with bus
    4. Create and register PrimeAgent (talks_to=None, unrestricted)
    5. Create and register micro-agents from profile (talks_to from config)
    6. Create Executor with bus
    7. Return (executor, bus, host)

    USER_SENDER is not registered on the bus. The bus explicitly
    allows it as a sender without registration (virtual sender).
    """
    ai = AILayer(config)
    bus = MessageBus()
    host = AgentHost(bus)

    # Prime agent
    prime = PrimeAgent(
        identity=profile.prime.identity,
        ai=ai,
        host=host,
        bus=bus,
    )
    host.register(prime, talks_to=None)

    # Micro-agents from profile
    for micro_config in profile.micro_agents:
        agent = MicroAgent(config=micro_config, ai=ai)
        # Always convert to set -- empty list [] becomes empty set() (talk to
        # nobody), not None (unrestricted). Only Prime gets talks_to=None.
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)

    executor = Executor(bus=bus)
    return executor, bus, host
