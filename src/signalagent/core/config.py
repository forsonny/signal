"""Configuration loading and instance management."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.errors import ConfigError, InstanceError
from signalagent.core.models import Profile, ToolConfig


class AIConfig(BaseModel):
    """AI layer configuration."""
    model_config = ConfigDict(extra="forbid")

    default_model: str = "anthropic/claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"


class SignalConfig(BaseModel):
    """Top-level Signal instance configuration."""
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    ai: AIConfig = Field(default_factory=AIConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)

    def to_yaml(self, path: Path) -> None:
        # NOTE: model_dump(mode="json") converts Path fields to strings.
        # Currently all fields are strings so this is fine. When Phase 2
        # adds Path fields for memory directories, this serialization
        # behavior should be revisited.
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
