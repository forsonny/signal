"""Core enums and type definitions for Signal."""

from enum import Enum


class AgentType(str, Enum):
    """Type of agent in the Signal system."""

    PRIME = "prime"
    MICRO = "micro"
    SUB = "sub"
    MEMORY_KEEPER = "memory_keeper"


class AgentStatus(str, Enum):
    """Lifecycle status of an agent."""

    CREATED = "created"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    KILLED = "killed"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Lifecycle status of a task."""

    CREATED = "created"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETING = "completing"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskPriority(int, Enum):
    """Task priority levels. Higher value = higher priority."""

    IDLE = 1
    LOW = 2
    NORMAL = 3
    HIGH = 4
    CRITICAL = 5


class MessageType(str, Enum):
    """Type of inter-agent message."""

    TASK = "task"
    RESULT = "result"
    REQUEST = "request"
    RESPONSE = "response"
    ESCALATION = "escalation"
    SPAWN = "spawn"
    REPORT = "report"
    TRIGGER = "trigger"
    MEMORY_WRITE = "memory_write"


class MemoryType(str, Enum):
    """Type of memory stored by an agent."""

    IDENTITY = "identity"
    LEARNING = "learning"
    PATTERN = "pattern"
    OUTCOME = "outcome"
    CONTEXT = "context"
    SHARED = "shared"


# Well-known agent/sender names. Used by the message bus for permission
# bypass and by the executor as the sender identity. Centralised here
# so no module uses magic strings.
PRIME_AGENT = "prime"
USER_SENDER = "user"
HEARTBEAT_SENDER = "heartbeat"
