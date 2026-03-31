"""Core data models for Signal profiles and agent configuration."""

from pydantic import BaseModel, Field


class PrimeConfig(BaseModel):
    """Configuration for the Prime Agent from a profile."""
    identity: str = (
        "You are a helpful AI assistant. The user will define "
        "your purpose and add specialist agents over time."
    )


class MicroAgentConfig(BaseModel):
    """Configuration for a micro-agent from a profile."""
    name: str
    skill: str
    talks_to: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    can_spawn_subs: bool = False


class PluginsConfig(BaseModel):
    """Available plugins configuration."""
    available: list[str] = Field(default_factory=list)


class HeartbeatConfig(BaseModel):
    """Heartbeat trigger configuration from a profile."""
    clock_triggers: list[dict] = Field(default_factory=list)
    event_triggers: list[dict] = Field(default_factory=list)
    condition_triggers: list[dict] = Field(default_factory=list)


class Profile(BaseModel):
    """A Signal profile -- defines what an instance becomes."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    prime: PrimeConfig = Field(default_factory=PrimeConfig)
    micro_agents: list[MicroAgentConfig] = Field(default_factory=list)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
