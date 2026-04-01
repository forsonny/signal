"""Core data models for Signal profiles and agent configuration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.types import MemoryType, MessageType


class PrimeConfig(BaseModel):
    """Configuration for the Prime Agent from a profile."""
    model_config = ConfigDict(extra="forbid")

    identity: str = (
        "You are a helpful AI assistant. The user will define "
        "your purpose and add specialist agents over time."
    )


class MicroAgentConfig(BaseModel):
    """Configuration for a micro-agent from a profile."""
    model_config = ConfigDict(extra="forbid")

    name: str
    skill: str
    talks_to: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    can_spawn_subs: bool = False
    max_iterations: int = Field(default=10, ge=1)


class PluginsConfig(BaseModel):
    """Available plugins configuration."""
    model_config = ConfigDict(extra="forbid")

    available: list[str] = Field(default_factory=list)


class HeartbeatConfig(BaseModel):
    """Heartbeat trigger configuration from a profile."""
    model_config = ConfigDict(extra="forbid")

    clock_triggers: list[dict] = Field(default_factory=list)
    event_triggers: list[dict] = Field(default_factory=list)
    condition_triggers: list[dict] = Field(default_factory=list)


class Profile(BaseModel):
    """A Signal profile -- defines what an instance becomes."""
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    prime: PrimeConfig = Field(default_factory=PrimeConfig)
    micro_agents: list[MicroAgentConfig] = Field(default_factory=list)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class Memory(BaseModel):
    """Atomic unit of agent knowledge."""
    model_config = ConfigDict(extra="forbid")

    id: str
    agent: str
    type: MemoryType
    tags: list[str] = Field(default_factory=list)
    content: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    version: int = 1
    created: datetime
    updated: datetime
    accessed: datetime
    access_count: int = 0
    changelog: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    consolidated_from: list[str] = Field(default_factory=list)


class Message(BaseModel):
    """Typed message passed between agents via the MessageBus."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    type: MessageType = Field(...)
    sender: str
    recipient: str
    content: str
    created: datetime | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """What the LLM wants to do -- a request to call a tool.

    Named ToolCallRequest (not ToolCall) to reserve ToolCall for the full
    execution record with result, timing, and tracing (Phase 10).
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result of executing a tool call."""
    model_config = ConfigDict(extra="forbid")

    output: str
    error: str | None = None


class ToolConfig(BaseModel):
    """Global tool execution settings."""
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=20, ge=1)
