from signalagent.core.types import (
    AgentType,
    AgentStatus,
    TaskStatus,
    TaskPriority,
    MessageType,
)


class TestAgentType:
    def test_values(self):
        assert AgentType.PRIME == "prime"
        assert AgentType.MICRO == "micro"
        assert AgentType.SUB == "sub"
        assert AgentType.MEMORY_KEEPER == "memory_keeper"

    def test_string_serialization(self):
        assert str(AgentType.PRIME) == "AgentType.PRIME"
        assert AgentType("prime") == AgentType.PRIME


class TestAgentStatus:
    def test_values(self):
        assert AgentStatus.CREATED == "created"
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.BUSY == "busy"
        assert AgentStatus.WAITING == "waiting"
        assert AgentStatus.KILLED == "killed"
        assert AgentStatus.ARCHIVED == "archived"


class TestTaskStatus:
    def test_values(self):
        assert TaskStatus.CREATED == "created"
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.ASSIGNED == "assigned"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.WAITING == "waiting"
        assert TaskStatus.COMPLETING == "completing"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.ARCHIVED == "archived"


class TestTaskPriority:
    def test_ordering(self):
        assert TaskPriority.IDLE < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.CRITICAL

    def test_values(self):
        assert TaskPriority.IDLE == 1
        assert TaskPriority.CRITICAL == 5


class TestMessageType:
    def test_values(self):
        assert MessageType.TASK == "task"
        assert MessageType.RESULT == "result"
        assert MessageType.ESCALATION == "escalation"
        assert MessageType.MEMORY_WRITE == "memory_write"
