# Phase 1: Skeleton -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `signal init --profile blank` creates an instance and `signal talk "hello"` sends a message through LiteLLM and prints the response.

**Architecture:** Minimal end-to-end pipeline. Config loads from YAML, AI layer wraps LiteLLM with a unified response, a simple executor takes a message and returns a response, CLI ties it together with Typer. No agents, no memory, no sessions -- just the skeleton that everything else builds on.

**Tech Stack:** Python 3.11+, uv, Pydantic v2, LiteLLM, Typer, Rich, aiosqlite, httpx, PyYAML, pytest, pytest-asyncio

---

## File Map

```
src/
└── signalagent/
    ├── __init__.py                 # Package version
    ├── core/
    │   ├── __init__.py
    │   ├── types.py                # Enums: AgentType, AgentStatus, TaskStatus, etc.
    │   ├── errors.py               # SignalError, ConfigError, AIError, InstanceError
    │   ├── models.py               # Profile, PrimeConfig, MicroAgentConfig, HeartbeatConfig
    │   └── config.py               # SignalConfig, AIConfig, find_instance, create_instance
    ├── ai/
    │   ├── __init__.py
    │   └── layer.py                # AILayer, AIResponse -- wraps LiteLLM
    ├── runtime/
    │   ├── __init__.py
    │   └── executor.py             # Executor -- message in, response out, error boundary
    ├── cli/
    │   ├── __init__.py
    │   ├── app.py                  # Typer app + main() entry point
    │   ├── init_cmd.py             # signal init --profile <name>
    │   └── talk_cmd.py             # signal talk "<message>"
    └── profiles/
        └── blank.yaml              # Built-in blank profile

tests/
├── conftest.py                     # Shared fixtures
├── unit/
│   ├── core/
│   │   ├── test_types.py
│   │   ├── test_models.py
│   │   └── test_config.py
│   ├── ai/
│   │   └── test_layer.py
│   └── runtime/
│       └── test_executor.py
└── integration/
    └── test_cli.py

pyproject.toml
.gitignore
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/signalagent/__init__.py`
- Create: all `__init__.py` files for subpackages
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "signalagent"
version = "0.1.0"
description = "AI agent runtime framework"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0,<3",
    "litellm>=1.40",
    "typer[all]>=0.9",
    "rich>=13.0",
    "aiosqlite>=0.19",
    "httpx>=0.25",
    "pyyaml>=6.0",
]

[project.scripts]
signal = "signalagent.cli.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/signalagent"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
]
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
.signal/
.superpowers/
*.db
.env
```

- [ ] **Step 3: Create package structure**

Create all `__init__.py` files:

```python
# src/signalagent/__init__.py
"""Signal -- AI agent runtime framework."""

__version__ = "0.1.0"
```

Create empty `__init__.py` in each of these directories:
- `src/signalagent/core/__init__.py`
- `src/signalagent/ai/__init__.py`
- `src/signalagent/runtime/__init__.py`
- `src/signalagent/cli/__init__.py`
- `src/signalagent/profiles/` (no `__init__.py` -- not a Python package, just data)
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/unit/core/__init__.py`
- `tests/unit/ai/__init__.py`
- `tests/unit/runtime/__init__.py`
- `tests/integration/__init__.py`

- [ ] **Step 4: Create minimal conftest.py**

```python
# tests/conftest.py
```

Empty for now. Fixtures added as needed.

- [ ] **Step 5: Initialize uv and verify**

Run:
```bash
cd C:/dev/signal
uv sync
uv run pytest --co -q
```

Expected: uv installs all dependencies, pytest collects 0 tests (no test files yet), exits cleanly.

- [ ] **Step 6: Initialize git and commit**

Run:
```bash
cd C:/dev/signal
git init
git add pyproject.toml .gitignore src/ tests/
git commit -m "feat: project scaffold with uv and package structure"
```

---

### Task 2: Core Types & Errors

**Files:**
- Create: `src/signalagent/core/types.py`
- Create: `src/signalagent/core/errors.py`
- Test: `tests/unit/core/test_types.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/test_types.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: ImportError -- module `signalagent.core.types` has no members yet.

- [ ] **Step 3: Implement types**

```python
# src/signalagent/core/types.py
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
```

- [ ] **Step 4: Implement errors**

```python
# src/signalagent/core/errors.py
"""Base exception hierarchy for Signal."""


class SignalError(Exception):
    """Base exception for all Signal errors."""


class ConfigError(SignalError):
    """Configuration loading or validation failed."""


class AIError(SignalError):
    """AI layer error -- LLM call failed, provider unavailable, etc."""


class InstanceError(SignalError):
    """Instance management error -- init, start, stop failures."""
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/core/types.py src/signalagent/core/errors.py tests/unit/core/test_types.py
git commit -m "feat: core enums (AgentType, TaskStatus, etc.) and error hierarchy"
```

---

### Task 3: Profile Model + Blank Profile

**Files:**
- Create: `src/signalagent/core/models.py`
- Create: `src/signalagent/profiles/blank.yaml`
- Test: `tests/unit/core/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/test_models.py
import yaml
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HeartbeatConfig,
)


class TestPrimeConfig:
    def test_defaults(self):
        config = PrimeConfig()
        assert "helpful" in config.identity.lower() or config.identity != ""

    def test_custom_identity(self):
        config = PrimeConfig(identity="You are a code review expert.")
        assert config.identity == "You are a code review expert."


class TestMicroAgentConfig:
    def test_minimal(self):
        agent = MicroAgentConfig(name="code-review", skill="Code quality")
        assert agent.name == "code-review"
        assert agent.skill == "Code quality"
        assert agent.talks_to == []
        assert agent.plugins == []
        assert agent.can_spawn_subs is False

    def test_full(self):
        agent = MicroAgentConfig(
            name="code-review",
            skill="Code quality, security",
            talks_to=["git", "testing"],
            plugins=["file_system"],
            can_spawn_subs=True,
        )
        assert agent.talks_to == ["git", "testing"]
        assert agent.can_spawn_subs is True


class TestProfile:
    def test_blank_profile(self):
        profile = Profile(name="blank", description="Empty instance")
        assert profile.name == "blank"
        assert profile.micro_agents == []
        assert profile.prime.identity != ""

    def test_devtools_profile(self):
        profile = Profile(
            name="devtools",
            description="Development assistant",
            prime=PrimeConfig(identity="You are a senior development partner."),
            micro_agents=[
                MicroAgentConfig(
                    name="code-review",
                    skill="Code quality",
                    talks_to=["git"],
                    plugins=["file_system"],
                ),
                MicroAgentConfig(
                    name="git",
                    skill="Version control",
                    talks_to=["code-review"],
                    plugins=["git"],
                ),
            ],
            plugins=PluginsConfig(available=["file_system", "git"]),
        )
        assert len(profile.micro_agents) == 2
        assert profile.micro_agents[0].name == "code-review"

    def test_from_yaml_string(self):
        yaml_str = """
name: test
description: Test profile
prime:
  identity: "You are a test agent."
micro_agents:
  - name: reviewer
    skill: "Code review"
    talks_to: [git]
    plugins: [file_system]
    can_spawn_subs: true
plugins:
  available: [file_system, git]
"""
        data = yaml.safe_load(yaml_str)
        profile = Profile(**data)
        assert profile.name == "test"
        assert len(profile.micro_agents) == 1
        assert profile.micro_agents[0].can_spawn_subs is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_models.py -v`
Expected: ImportError -- `signalagent.core.models` does not exist.

- [ ] **Step 3: Implement models**

```python
# src/signalagent/core/models.py
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
```

- [ ] **Step 4: Create blank profile**

```yaml
# src/signalagent/profiles/blank.yaml
name: blank
description: Empty Signal instance -- build your own
version: 1.0.0

prime:
  identity: >
    You are a helpful AI assistant. The user will define
    your purpose and add specialist agents over time.

micro_agents: []

plugins:
  available: [file_system, bash, web_search]
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/core/test_models.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/core/models.py src/signalagent/profiles/blank.yaml tests/unit/core/test_models.py
git commit -m "feat: Profile and agent config models with blank profile"
```

---

### Task 4: Config & Instance Management

**Files:**
- Create: `src/signalagent/core/config.py`
- Test: `tests/unit/core/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/test_config.py
import yaml
from pathlib import Path

from signalagent.core.config import (
    AIConfig,
    SignalConfig,
    create_instance,
    find_instance,
    load_config,
    load_profile,
)
from signalagent.core.errors import ConfigError, InstanceError


class TestAIConfig:
    def test_defaults(self):
        config = AIConfig()
        assert "claude" in config.default_model or config.default_model != ""
        assert config.api_key_env == "ANTHROPIC_API_KEY"

    def test_custom(self):
        config = AIConfig(
            default_model="openai/gpt-4o",
            api_key_env="OPENAI_API_KEY",
        )
        assert config.default_model == "openai/gpt-4o"


class TestSignalConfig:
    def test_defaults(self):
        config = SignalConfig(profile_name="blank")
        assert config.profile_name == "blank"
        assert isinstance(config.ai, AIConfig)

    def test_to_yaml_and_load(self, tmp_path):
        config = SignalConfig(
            profile_name="devtools",
            ai=AIConfig(default_model="openai/gpt-4o"),
        )
        path = tmp_path / "config.yaml"
        config.to_yaml(path)

        loaded = load_config(path)
        assert loaded.profile_name == "devtools"
        assert loaded.ai.default_model == "openai/gpt-4o"


class TestLoadProfile:
    def test_load_builtin_blank(self):
        profile = load_profile("blank")
        assert profile.name == "blank"
        assert profile.prime.identity != ""

    def test_load_from_path(self, tmp_path):
        profile_path = tmp_path / "custom.yaml"
        profile_path.write_text(
            yaml.dump({"name": "custom", "description": "Custom profile"})
        )
        profile = load_profile(str(profile_path))
        assert profile.name == "custom"

    def test_load_nonexistent_raises(self):
        import pytest

        with pytest.raises(ConfigError, match="Profile not found"):
            load_profile("nonexistent_profile_xyz")


class TestCreateInstance:
    def test_creates_directory_structure(self, tmp_path):
        instance_dir = tmp_path / ".signal"
        create_instance(instance_dir, "blank")

        assert instance_dir.exists()
        assert (instance_dir / "config.yaml").exists()
        assert (instance_dir / "data").is_dir()
        assert (instance_dir / "memory").is_dir()
        assert (instance_dir / "memory" / "prime").is_dir()
        assert (instance_dir / "memory" / "micro").is_dir()
        assert (instance_dir / "memory" / "shared").is_dir()
        assert (instance_dir / "logs").is_dir()

    def test_config_contains_profile_name(self, tmp_path):
        instance_dir = tmp_path / ".signal"
        create_instance(instance_dir, "blank")

        config = load_config(instance_dir / "config.yaml")
        assert config.profile_name == "blank"

    def test_raises_if_already_exists(self, tmp_path):
        import pytest

        instance_dir = tmp_path / ".signal"
        create_instance(instance_dir, "blank")

        with pytest.raises(InstanceError, match="already exists"):
            create_instance(instance_dir, "blank")


class TestFindInstance:
    def test_finds_in_current_dir(self, tmp_path):
        instance_dir = tmp_path / ".signal"
        create_instance(instance_dir, "blank")

        found = find_instance(tmp_path)
        assert found == instance_dir

    def test_raises_if_not_found(self, tmp_path):
        import pytest

        with pytest.raises(InstanceError, match="No Signal instance found"):
            find_instance(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_config.py -v`
Expected: ImportError -- `signalagent.core.config` does not exist.

- [ ] **Step 3: Implement config**

```python
# src/signalagent/core/config.py
"""Configuration loading and instance management."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from signalagent.core.errors import ConfigError, InstanceError
from signalagent.core.models import Profile


class AIConfig(BaseModel):
    """AI layer configuration."""

    default_model: str = "anthropic/claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"


class SignalConfig(BaseModel):
    """Top-level Signal instance configuration."""

    profile_name: str
    ai: AIConfig = Field(default_factory=AIConfig)

    def to_yaml(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                self.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
            )


def load_config(path: Path) -> SignalConfig:
    """Load a SignalConfig from a YAML file."""
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return SignalConfig(**data)


def load_profile(name_or_path: str) -> Profile:
    """Load a profile by name (built-in) or by file path."""
    path = Path(name_or_path)
    if path.exists() and path.suffix in (".yaml", ".yml"):
        with open(path) as f:
            data = yaml.safe_load(f)
        return Profile(**data)

    profiles_dir = importlib.resources.files("signalagent") / "profiles"
    builtin = profiles_dir / f"{name_or_path}.yaml"
    if builtin.is_file():
        with open(str(builtin)) as f:
            data = yaml.safe_load(f)
        return Profile(**data)

    raise ConfigError(f"Profile not found: {name_or_path}")


def create_instance(instance_dir: Path, profile_name: str) -> None:
    """Create a new Signal instance directory with config and subdirectories."""
    if instance_dir.exists():
        raise InstanceError(f"Signal instance already exists: {instance_dir}")

    instance_dir.mkdir(parents=True)

    for subdir in [
        "data",
        "data/runtime",
        "data/sessions",
        "data/tasks",
        "memory",
        "memory/prime",
        "memory/micro",
        "memory/shared",
        "triggers",
        "triggers/static",
        "triggers/dynamic",
        "plugins",
        "logs",
    ]:
        (instance_dir / subdir).mkdir(parents=True, exist_ok=True)

    config = SignalConfig(profile_name=profile_name)
    config.to_yaml(instance_dir / "config.yaml")


def find_instance(start_dir: Path) -> Path:
    """Find a Signal instance directory by searching from start_dir upward."""
    current = start_dir.resolve()
    while True:
        candidate = current / ".signal"
        if candidate.is_dir() and (candidate / "config.yaml").exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise InstanceError(
        "No Signal instance found. Run 'signal init' to create one."
    )
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/unit/core/test_config.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/core/config.py tests/unit/core/test_config.py
git commit -m "feat: config loading, profile resolution, and instance management"
```

---

### Task 5: AI Layer

**Files:**
- Create: `src/signalagent/ai/layer.py`
- Test: `tests/unit/ai/test_layer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ai/test_layer.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from signalagent.ai.layer import AILayer, AIResponse
from signalagent.core.config import AIConfig, SignalConfig
from signalagent.core.errors import AIError


class TestAIResponse:
    def test_fields(self):
        resp = AIResponse(
            content="Hello!",
            model="anthropic/claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            cost=0.001,
        )
        assert resp.content == "Hello!"
        assert resp.input_tokens == 10

    def test_defaults(self):
        resp = AIResponse(
            content="Hi", model="test", provider="test"
        )
        assert resp.input_tokens == 0
        assert resp.cost == 0.0


def _mock_litellm_response(content="Hello! How can I help?"):
    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    response.usage = MagicMock(prompt_tokens=15, completion_tokens=25)
    response.model = "anthropic/claude-sonnet-4-20250514"
    return response


class TestAILayer:
    @pytest.fixture
    def config(self):
        return SignalConfig(profile_name="blank")

    @pytest.fixture
    def layer(self, config):
        return AILayer(config)

    @pytest.mark.asyncio
    async def test_complete_returns_response(self, layer):
        mock_resp = _mock_litellm_response("Test response")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            result = await layer.complete(
                messages=[{"role": "user", "content": "hello"}]
            )
        assert isinstance(result, AIResponse)
        assert result.content == "Test response"
        assert result.input_tokens == 15
        assert result.output_tokens == 25
        assert result.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_complete_uses_default_model(self, layer):
        mock_resp = _mock_litellm_response()
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp) as mock_call:
            await layer.complete(
                messages=[{"role": "user", "content": "hello"}]
            )
        call_kwargs = mock_call.call_args
        assert call_kwargs.kwargs["model"] == "anthropic/claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_complete_uses_override_model(self, layer):
        mock_resp = _mock_litellm_response()
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp) as mock_call:
            await layer.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="openai/gpt-4o",
            )
        call_kwargs = mock_call.call_args
        assert call_kwargs.kwargs["model"] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_complete_wraps_errors(self, layer):
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("API down")):
            with pytest.raises(AIError, match="LLM call failed"):
                await layer.complete(
                    messages=[{"role": "user", "content": "hello"}]
                )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/ai/test_layer.py -v`
Expected: ImportError -- `signalagent.ai.layer` does not exist.

- [ ] **Step 3: Implement AI layer**

```python
# src/signalagent/ai/layer.py
"""AI layer -- unified interface to LLM providers via LiteLLM."""

from __future__ import annotations

from typing import Optional

import litellm
from pydantic import BaseModel

from signalagent.core.config import SignalConfig
from signalagent.core.errors import AIError

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True


class AIResponse(BaseModel):
    """Unified response from any LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class AILayer:
    """Wraps LiteLLM to provide a unified LLM interface for all agents."""

    def __init__(self, config: SignalConfig) -> None:
        self._config = config

    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> AIResponse:
        """Send a completion request to an LLM provider.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model identifier (e.g. "anthropic/claude-sonnet-4-20250514").
                   Falls back to config default.

        Returns:
            Unified AIResponse regardless of provider.

        Raises:
            AIError: If the LLM call fails for any reason.
        """
        model = model or self._config.ai.default_model
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
            )
        except Exception as e:
            raise AIError(f"LLM call failed: {e}") from e

        choice = response.choices[0]
        usage = response.usage

        provider = model.split("/")[0] if "/" in model else "unknown"

        cost = 0.0
        try:
            cost = litellm.completion_cost(completion_response=response) or 0.0
        except Exception:
            pass

        return AIResponse(
            content=choice.message.content or "",
            model=response.model or model,
            provider=provider,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cost=cost,
        )
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/unit/ai/test_layer.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/ai/layer.py tests/unit/ai/test_layer.py
git commit -m "feat: AI layer wrapping LiteLLM with unified response format"
```

---

### Task 6: Single-Agent Executor

**Files:**
- Create: `src/signalagent/runtime/executor.py`
- Test: `tests/unit/runtime/test_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/runtime/test_executor.py
import pytest
from unittest.mock import AsyncMock

from signalagent.ai.layer import AIResponse
from signalagent.core.models import PrimeConfig, Profile
from signalagent.runtime.executor import Executor


def _make_profile(identity: str = "You are a test assistant.") -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity=identity),
    )


def _make_ai_response(content: str = "Test response") -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


class TestExecutor:
    @pytest.mark.asyncio
    async def test_run_returns_content(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("Hello!"))

        executor = Executor(ai=mock_ai, profile=_make_profile())
        result = await executor.run("hi")

        assert result.content == "Hello!"

    @pytest.mark.asyncio
    async def test_run_sends_system_prompt(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response())

        executor = Executor(
            ai=mock_ai,
            profile=_make_profile("You are a pirate."),
        )
        await executor.run("hello")

        call_args = mock_ai.complete.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a pirate."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_run_error_boundary(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=Exception("LLM exploded"))

        executor = Executor(ai=mock_ai, profile=_make_profile())
        result = await executor.run("hello")

        assert result.content == ""
        assert result.error is not None
        assert "LLM exploded" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/runtime/test_executor.py -v`
Expected: ImportError -- `signalagent.runtime.executor` does not exist.

- [ ] **Step 3: Implement executor**

```python
# src/signalagent/runtime/executor.py
"""Single-agent executor -- the minimal agentic loop for Phase 1."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Protocol

from signalagent.core.models import Profile

logger = logging.getLogger(__name__)


class AILayerProtocol(Protocol):
    """Protocol for the AI layer so executor doesn't depend on concrete class."""

    async def complete(self, messages: list[dict], **kwargs) -> "AIResponseLike": ...


@dataclass
class ExecutorResult:
    """Result of an executor run."""

    content: str
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class Executor:
    """Minimal executor: takes a user message, builds a prompt, calls the AI layer, returns a result.

    Error boundary: exceptions from the AI layer are caught, logged,
    and returned as an ExecutorResult with error set. The caller never
    sees an unhandled exception from here.
    """

    def __init__(self, ai: AILayerProtocol, profile: Profile) -> None:
        self._ai = ai
        self._profile = profile

    async def run(self, user_message: str) -> ExecutorResult:
        """Execute a single message through the AI layer.

        Args:
            user_message: The user's input text.

        Returns:
            ExecutorResult with content or error. Never raises.
        """
        messages = [
            {"role": "system", "content": self._profile.prime.identity},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self._ai.complete(messages=messages)
            return ExecutorResult(
                content=response.content,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost=response.cost,
            )
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(content="", error=str(e))
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/unit/runtime/test_executor.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/runtime/executor.py tests/unit/runtime/test_executor.py
git commit -m "feat: single-agent executor with error boundary"
```

---

### Task 7: CLI Init Command

**Files:**
- Create: `src/signalagent/cli/app.py`
- Create: `src/signalagent/cli/init_cmd.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_cli.py
import os
from pathlib import Path

import yaml
from typer.testing import CliRunner

from signalagent.cli.app import app

runner = CliRunner()


class TestInitCommand:
    def test_init_creates_instance(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / ".signal").is_dir()
        assert (tmp_path / ".signal" / "config.yaml").exists()

    def test_init_with_profile(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init", "--profile", "blank"])

        assert result.exit_code == 0
        config_path = tmp_path / ".signal" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["profile_name"] == "blank"

    def test_init_fails_if_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["init"])

        assert result.exit_code == 1
        assert "already exists" in result.stdout.lower()

    def test_init_creates_subdirectories(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["init"])

        assert (tmp_path / ".signal" / "memory" / "prime").is_dir()
        assert (tmp_path / ".signal" / "memory" / "micro").is_dir()
        assert (tmp_path / ".signal" / "data").is_dir()
        assert (tmp_path / ".signal" / "logs").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli.py::TestInitCommand -v`
Expected: ImportError -- `signalagent.cli.app` does not exist.

- [ ] **Step 3: Implement CLI app and init command**

```python
# src/signalagent/cli/app.py
"""Signal CLI -- entry point for all commands."""

import typer

app = typer.Typer(
    name="signal",
    help="Signal -- AI agent runtime framework",
    no_args_is_help=True,
)


def _register_commands() -> None:
    """Import command modules so their @app.command() decorators execute.

    Safe to call at module level because `app` is already defined above.
    The command modules import `app` from this module -- Python resolves
    this correctly since `app` is assigned before this function runs.
    """
    import signalagent.cli.init_cmd  # noqa: F401
    import signalagent.cli.talk_cmd  # noqa: F401


_register_commands()


def main() -> None:
    """Entry point for the signal CLI."""
    app()
```

```python
# src/signalagent/cli/init_cmd.py
"""signal init -- create a new Signal instance."""

from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.config import create_instance, load_profile
from signalagent.core.errors import ConfigError, InstanceError

console = Console()


@app.command()
def init(
    profile: str = typer.Option("blank", help="Profile to initialize with"),
) -> None:
    """Initialize a new Signal instance in the current directory."""
    instance_dir = Path.cwd() / ".signal"

    try:
        load_profile(profile)
    except ConfigError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    try:
        create_instance(instance_dir, profile)
    except InstanceError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]Signal instance initialized with profile '{profile}'[/green]"
    )
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/integration/test_cli.py::TestInitCommand -v`
Expected: All tests pass.

```bash
git add src/signalagent/cli/app.py src/signalagent/cli/init_cmd.py tests/integration/test_cli.py
git commit -m "feat: CLI init command creates Signal instance"
```

---

### Task 8: CLI Talk Command

**Files:**
- Create: `src/signalagent/cli/talk_cmd.py`
- Modify: `tests/integration/test_cli.py` (add TestTalkCommand)

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_cli.py`:

```python
from unittest.mock import AsyncMock, patch

from signalagent.ai.layer import AIResponse


def _mock_ai_response(content="Hello from Signal!"):
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


class TestTalkCommand:
    def test_talk_one_shot(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        with patch(
            "signalagent.cli.talk_cmd._run_talk",
            return_value="Hello from Signal!",
        ):
            result = runner.invoke(app, ["talk", "hello"])

        assert result.exit_code == 0
        assert "Hello from Signal!" in result.stdout

    def test_talk_no_instance(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["talk", "hello"])

        assert result.exit_code == 1
        assert "no signal instance" in result.stdout.lower()

    def test_talk_requires_message(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["talk"])

        assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli.py::TestTalkCommand -v`
Expected: Fails -- `talk_cmd` not implemented.

- [ ] **Step 3: Implement talk command**

```python
# src/signalagent/cli/talk_cmd.py
"""signal talk -- send a message to Signal."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.config import find_instance, load_config, load_profile
from signalagent.core.errors import InstanceError

console = Console()


def _run_talk(message: str, instance_dir: Path) -> str:
    """Run the talk pipeline synchronously (wraps async internals)."""
    return asyncio.run(_async_talk(message, instance_dir))


async def _async_talk(message: str, instance_dir: Path) -> str:
    """Async implementation of the talk pipeline."""
    from signalagent.ai.layer import AILayer
    from signalagent.runtime.executor import Executor

    config = load_config(instance_dir / "config.yaml")
    profile = load_profile(config.profile_name)
    ai = AILayer(config)
    executor = Executor(ai=ai, profile=profile)

    result = await executor.run(message)

    if result.error:
        return f"Error: {result.error}"

    return result.content


@app.command()
def talk(
    message: str = typer.Argument(..., help="Message to send"),
) -> None:
    """Send a one-shot message to Signal."""
    try:
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    response = _run_talk(message, instance_dir)
    console.print(response)
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/integration/test_cli.py -v`
Expected: All tests pass.

```bash
git add src/signalagent/cli/talk_cmd.py tests/integration/test_cli.py
git commit -m "feat: CLI talk command for one-shot messages"
```

---

### Task 9: End-to-End Integration Test

**Files:**
- Modify: `tests/integration/test_cli.py` (add TestEndToEnd)
- Modify: `tests/conftest.py` (add shared fixtures)

- [ ] **Step 1: Add shared fixtures to conftest**

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock

from signalagent.ai.layer import AIResponse


@pytest.fixture
def mock_ai_response():
    """Create a mock LiteLLM response object."""
    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content="I'm Signal, ready to help!"))
    ]
    response.usage = MagicMock(prompt_tokens=20, completion_tokens=30)
    response.model = "anthropic/claude-sonnet-4-20250514"
    return response
```

- [ ] **Step 2: Write the end-to-end test**

Add to `tests/integration/test_cli.py`:

```python
class TestEndToEnd:
    """Full pipeline: init -> talk with mocked LLM."""

    def test_init_then_talk(self, tmp_path, monkeypatch, mock_ai_response):
        monkeypatch.chdir(tmp_path)

        # Step 1: init
        init_result = runner.invoke(app, ["init", "--profile", "blank"])
        assert init_result.exit_code == 0
        assert (tmp_path / ".signal").exists()

        # Step 2: talk with mocked LLM
        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_ai_response,
        ):
            talk_result = runner.invoke(app, ["talk", "hello"])

        assert talk_result.exit_code == 0
        assert "Signal, ready to help" in talk_result.stdout

    def test_talk_shows_error_on_ai_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=Exception("Provider unavailable"),
        ):
            result = runner.invoke(app, ["talk", "hello"])

        assert result.exit_code == 0
        assert "error" in result.stdout.lower()
```

- [ ] **Step 3: Add missing import to test file**

At the top of `tests/integration/test_cli.py`, ensure these imports are present:

```python
from unittest.mock import AsyncMock, patch
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass across all test files.

```
tests/unit/core/test_types.py       -- PASSED (all enum tests)
tests/unit/core/test_models.py      -- PASSED (profile/config models)
tests/unit/core/test_config.py      -- PASSED (config load/save, instance)
tests/unit/ai/test_layer.py         -- PASSED (AI layer with mocks)
tests/unit/runtime/test_executor.py -- PASSED (executor + error boundary)
tests/integration/test_cli.py       -- PASSED (init, talk, end-to-end)
```

- [ ] **Step 5: Final commit**

```bash
git add tests/conftest.py tests/integration/test_cli.py
git commit -m "feat: end-to-end integration tests for init + talk pipeline"
```

---

## Phase 1 Complete Checklist

After all tasks are done, verify:

- [ ] `uv run signal init --profile blank` creates `.signal/` with config and subdirectories
- [ ] `uv run signal talk "hello"` sends to LLM and prints response (requires API key in env)
- [ ] `uv run pytest -v` -- all tests pass
- [ ] Error boundary works: AI failures return error messages, don't crash
- [ ] Config loads from YAML, profile loads from built-in or file path
- [ ] Instance detection walks up directory tree

**What Phase 1 does NOT have (deferred to later phases):**
- No memory system (Phase 2)
- No multi-agent routing (Phase 3)
- No tool calls or agentic loop (Phase 4)
- No sessions or interactive mode (Phase 6)
- No Docker (Phase 10)
