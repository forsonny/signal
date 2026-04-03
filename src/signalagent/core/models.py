"""Core data models for Signal profiles and agent configuration.

Every cross-boundary data structure lives here so that packages depend on
``core.models`` rather than on each other. Pydantic v2 ``BaseModel``
subclasses with ``extra="forbid"`` enforce strict schema compliance.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.types import MemoryType, MessageType
from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger


class PrimeConfig(BaseModel):
    """Configuration for the Prime Agent from a profile.

    Controls the Prime agent's system-prompt identity. Loaded from the
    ``prime:`` section of a profile YAML file.
    """
    model_config = ConfigDict(extra="forbid")

    identity: str = Field(
        default=(
            "You are a helpful AI assistant. The user will define "
            "your purpose and add specialist agents over time."
        ),
        description="System prompt identity for Prime.",
    )


class MicroAgentConfig(BaseModel):
    """Configuration for a micro-agent from a profile.

    Each entry in the profile's ``micro_agents`` list becomes one of these.
    Defines the agent's skill, routing permissions, and tool access.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique agent name used for routing and memory scoping.")
    skill: str = Field(description="One-line description of what this agent does.")
    talks_to: list[str] = Field(default_factory=list, description="Agent names this agent can send messages to.")
    plugins: list[str] = Field(default_factory=list, description="Tool plugin names this agent can use.")
    mcp_servers: list[str] = Field(default_factory=list, description="MCP server names this agent connects to.")
    scripts: list[str] = Field(default_factory=list, description="Script paths this agent can execute.")
    can_spawn_subs: bool = Field(default=False, description="Whether this agent can spawn sub-agents.")
    max_iterations: int = Field(default=10, ge=1, description="Max agentic loop iterations for this agent.")


class PluginsConfig(BaseModel):
    """Available plugins configuration.

    Lists tool plugin names that are loaded at bootstrap and made
    available to agents via the ToolRegistry.
    """
    model_config = ConfigDict(extra="forbid")

    available: list[str] = Field(default_factory=list, description="Tool plugin names to load at startup.")


class HeartbeatConfig(BaseModel):
    """Heartbeat trigger configuration from a profile.

    Defines cron-based and file-event-based triggers that fire messages
    into the MessageBus on a schedule.
    """
    model_config = ConfigDict(extra="forbid")

    clock_triggers: list[ClockTrigger] = Field(default_factory=list, description="Cron-based recurring triggers.")
    event_triggers: list[FileEventTrigger] = Field(default_factory=list, description="Filesystem event triggers.")


class HooksConfig(BaseModel):
    """Active hooks configuration -- instance-wide tool call interception.

    Hooks run before and/or after every tool call, enabling logging,
    policy enforcement, and side-effects.
    """
    model_config = ConfigDict(extra="forbid")

    active: list[str] = Field(default_factory=list, description="Hook names to activate at startup.")


class ForkConfig(BaseModel):
    """Fork execution configuration -- parallel approach exploration.

    Controls how many worktree branches can run concurrently when an
    agent explores multiple solution paths.
    """
    model_config = ConfigDict(extra="forbid")

    max_concurrent_branches: int = Field(default=2, ge=1, description="Max parallel worktree branches.")


class MemoryConfig(BaseModel):
    """Memory retrieval configuration -- decay and scoring.

    Tunes how aggressively old memories lose relevance and which
    embedding model (if any) powers semantic search.
    """
    model_config = ConfigDict(extra="forbid")

    decay_half_life_days: int = Field(default=30, ge=1, description="Days after which memory relevance is halved.")
    embedding_model: str | None = Field(default=None, description="LiteLLM model ID for embeddings, or None to disable.")


class MemoryKeeperConfig(BaseModel):
    """MemoryKeeper agent configuration -- maintenance schedule and thresholds.

    When present in a profile, a MemoryKeeperAgent is registered and
    scheduled via the heartbeat system.
    """
    model_config = ConfigDict(extra="forbid")

    schedule: str = Field(default="0 3 * * 0", description="Cron expression for maintenance runs.")
    staleness_threshold_days: int = Field(default=90, ge=1, description="Days without access before a memory is stale.")
    min_confidence: float = Field(default=0.1, ge=0.0, le=1.0, description="Effective confidence below which stale memories are archived.")
    max_candidates_per_run: int = Field(default=20, ge=1, description="Max memory groups to process per maintenance run.")


class AgentPolicy(BaseModel):
    """Policy rules for a single agent -- tool access and memory scoping.

    When ``allow_tools`` or ``allow_memory_read`` is None the agent has
    unrestricted access; an empty list means no access.
    """
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(description="Agent name this policy applies to.")
    allow_tools: list[str] | None = Field(default=None, description="Allowed tool names, or None for unrestricted.")
    allow_memory_read: list[str] | None = Field(default=None, description="Allowed memory agent scopes, or None for unrestricted.")


class SecurityConfig(BaseModel):
    """Declarative security policies -- allow-list rules per agent.

    Evaluated by the PolicyEngine at tool-call time and by the
    PolicyMemoryReader at memory-search time.
    """
    model_config = ConfigDict(extra="forbid")

    policies: list[AgentPolicy] = Field(default_factory=list, description="Per-agent security policies.")


class Profile(BaseModel):
    """A Signal profile -- defines what an instance becomes.

    Loaded from a YAML file (built-in or user-supplied) and used by
    bootstrap to wire up agents, tools, hooks, and memory.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Profile name, used for display and lookup.")
    description: str = Field(default="", description="Human-readable profile description.")
    version: str = Field(default="1.0.0", description="Semantic version of this profile.")
    author: str = Field(default="", description="Profile author name or identifier.")
    prime: PrimeConfig = Field(default_factory=PrimeConfig, description="Prime agent configuration.")
    micro_agents: list[MicroAgentConfig] = Field(default_factory=list, description="Micro-agent definitions.")
    plugins: PluginsConfig = Field(default_factory=PluginsConfig, description="Available tool plugins.")
    hooks: HooksConfig = Field(default_factory=HooksConfig, description="Active hook configuration.")
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig, description="Heartbeat trigger configuration.")
    fork: ForkConfig = Field(default_factory=ForkConfig, description="Fork/worktree execution settings.")
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="Memory retrieval tuning.")
    memory_keeper: MemoryKeeperConfig | None = Field(default=None, description="MemoryKeeper agent config, or None to disable.")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="Security policy rules.")


class Memory(BaseModel):
    """Atomic unit of agent knowledge.

    Stored as a markdown file with YAML frontmatter on disk, indexed in
    SQLite for fast retrieval. Immutable once created -- updates produce
    new versions with changelog entries.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique memory identifier (mem_ + 8 hex chars).")
    agent: str = Field(description="Owning agent name for scoping.")
    type: MemoryType = Field(description="Category of knowledge this memory represents.")
    tags: list[str] = Field(default_factory=list, description="Searchable tags for retrieval.")
    content: str = Field(description="The memory's textual content.")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5, description="Confidence score from 0.0 to 1.0.")
    version: int = Field(default=1, description="Monotonically increasing version number.")
    created: datetime = Field(description="UTC timestamp when the memory was first created.")
    updated: datetime = Field(description="UTC timestamp of the last modification.")
    accessed: datetime = Field(description="UTC timestamp of the last read access.")
    access_count: int = Field(default=0, description="Total number of times this memory has been read.")
    changelog: list[str] = Field(default_factory=list, description="Version history entries.")
    supersedes: list[str] = Field(default_factory=list, description="IDs of memories this one replaces.")
    superseded_by: str | None = Field(default=None, description="ID of the memory that replaced this one.")
    consolidated_from: list[str] = Field(default_factory=list, description="Source memory IDs if this was created by consolidation.")


class Message(BaseModel):
    """Typed message passed between agents via the MessageBus.

    The fundamental unit of inter-agent communication. Carries the
    payload, routing info, and optional conversation history.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", description="Message identifier, auto-generated by the bus.")
    type: MessageType = Field(..., description="Message type controlling routing and handling.")
    sender: str = Field(description="Name of the sending agent or 'user'.")
    recipient: str = Field(description="Name of the target agent.")
    content: str = Field(description="Message payload text.")
    created: datetime | None = Field(default=None, description="UTC timestamp, set by the bus on send.")
    parent_id: str | None = Field(default=None, description="ID of the message this replies to.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value metadata.")
    history: list[dict[str, Any]] = Field(default_factory=list, description="Conversation history for multi-turn context.")


class Turn(BaseModel):
    """A single conversational turn at the Prime level.

    Captures what the user said and what Prime responded. Internal agent
    execution (tool calls, micro-agent delegation) is invisible at this
    level -- it's contained within a single assistant turn. If a future
    phase needs to replay internal tool chains, Turn would need extending.
    """
    model_config = ConfigDict(extra="forbid")

    role: str = Field(description="Turn role: 'user' or 'assistant'.")
    content: str = Field(description="Text content of this turn.")
    timestamp: datetime = Field(description="UTC timestamp when this turn occurred.")


class SessionSummary(BaseModel):
    """Lightweight session listing entry.

    Returned by the session manager when listing available sessions.
    Contains just enough info for display without loading full history.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Session identifier.")
    created: datetime = Field(description="UTC timestamp when the session started.")
    preview: str = Field(description="First user message or truncated summary.")
    turn_count: int = Field(description="Number of turns in the session.")


class ToolCallRequest(BaseModel):
    """What the LLM wants to do -- a request to call a tool.

    Named ToolCallRequest (not ToolCall) to reserve ToolCall for the full
    execution record with result, timing, and tracing (Phase 10).
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Tool call ID from the LLM response.")
    name: str = Field(description="Name of the tool to invoke.")
    arguments: dict[str, Any] = Field(description="Parsed arguments for the tool call.")


class ToolResult(BaseModel):
    """Result of executing a tool call.

    Returned by tool executors and hook pipelines. Exactly one of
    ``output`` or ``error`` carries the meaningful value.
    """
    model_config = ConfigDict(extra="forbid")

    output: str = Field(description="Tool output on success.")
    error: str | None = Field(default=None, description="Error message on failure, or None on success.")


class ToolConfig(BaseModel):
    """Global tool execution settings.

    Applied as a cap on per-agent max_iterations to prevent runaway loops.
    """
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=20, ge=1, description="Global max agentic loop iterations.")
