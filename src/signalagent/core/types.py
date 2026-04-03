"""Core enums and type definitions for Signal.

Defines the vocabulary of agent types, statuses, task lifecycle states,
message types, and memory categories used throughout the runtime.
"""

from enum import Enum


class AgentType(str, Enum):
    """Type of agent in the Signal system.

    Determines registration behavior and routing rules in the AgentHost.
    """

    PRIME = "prime"
    MICRO = "micro"
    SUB = "sub"
    MEMORY_KEEPER = "memory_keeper"


class AgentStatus(str, Enum):
    """Lifecycle status of an agent.

    Managed by BaseAgent's template method -- transitions automatically
    between BUSY and IDLE around message handling.
    """

    CREATED = "created"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    KILLED = "killed"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Lifecycle status of a task.

    Tracks a task from creation through execution to completion or archival.
    """

    CREATED = "created"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETING = "completing"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskPriority(int, Enum):
    """Task priority levels. Higher value = higher priority.

    Used by the task scheduler to determine execution order.
    """

    IDLE = 1
    LOW = 2
    NORMAL = 3
    HIGH = 4
    CRITICAL = 5


class MessageType(str, Enum):
    """Type of inter-agent message.

    Determines how the MessageBus routes and how agents interpret payloads.
    """

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
    """Type of memory stored by an agent.

    Controls file-path routing in MemoryStorage and scoping in search queries.
    """

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
