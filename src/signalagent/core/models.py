"""Core data models for Signal profiles and agent configuration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.types import MemoryType, MessageType
from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger


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

    clock_triggers: list[ClockTrigger] = Field(default_factory=list)
    event_triggers: list[FileEventTrigger] = Field(default_factory=list)


class HooksConfig(BaseModel):
    """Active hooks configuration -- instance-wide tool call interception."""
    model_config = ConfigDict(extra="forbid")

    active: list[str] = Field(default_factory=list)


class ForkConfig(BaseModel):
    """Fork execution configuration -- parallel approach exploration."""
    model_config = ConfigDict(extra="forbid")

    max_concurrent_branches: int = Field(default=2, ge=1)


class MemoryConfig(BaseModel):
    """Memory retrieval configuration -- decay and scoring."""
    model_config = ConfigDict(extra="forbid")

    decay_half_life_days: int = Field(default=30, ge=1)
    embedding_model: str | None = None


class MemoryKeeperConfig(BaseModel):
    """MemoryKeeper agent configuration -- maintenance schedule and thresholds."""
    model_config = ConfigDict(extra="forbid")

    schedule: str = "0 3 * * 0"
    staleness_threshold_days: int = Field(default=90, ge=1)
    min_confidence: float = Field(default=0.1, ge=0.0, le=1.0)
    max_candidates_per_run: int = Field(default=20, ge=1)


class AgentPolicy(BaseModel):
    """Policy rules for a single agent -- tool access and memory scoping."""
    model_config = ConfigDict(extra="forbid")

    agent: str
    allow_tools: list[str] | None = None
    allow_memory_read: list[str] | None = None


class SecurityConfig(BaseModel):
    """Declarative security policies -- allow-list rules per agent."""
    model_config = ConfigDict(extra="forbid")

    policies: list[AgentPolicy] = Field(default_factory=list)


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
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    fork: ForkConfig = Field(default_factory=ForkConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    memory_keeper: MemoryKeeperConfig | None = None
    security: SecurityConfig = Field(default_factory=SecurityConfig)


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
    history: list[dict[str, Any]] = Field(default_factory=list)


class Turn(BaseModel):
    """A single conversational turn at the Prime level.

    Captures what the user said and what Prime responded. Internal agent
    execution (tool calls, micro-agent delegation) is invisible at this
    level -- it's contained within a single assistant turn. If a future
    phase needs to replay internal tool chains, Turn would need extending.
    """
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    timestamp: datetime


class SessionSummary(BaseModel):
    """Lightweight session listing entry."""
    model_config = ConfigDict(extra="forbid")

    id: str
    created: datetime
    preview: str
    turn_count: int


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
