"""Configuration loading and instance management.

Handles YAML config files, profile resolution (built-in or user-supplied),
and instance directory creation with the standard subdirectory layout.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.errors import ConfigError, InstanceError
from signalagent.core.models import Profile, ToolConfig


class AIConfig(BaseModel):
    """AI layer configuration.

    Controls which LLM model and API key environment variable are used
    by the AILayer at runtime.
    """
    model_config = ConfigDict(extra="forbid")

    default_model: str = Field(default="anthropic/claude-sonnet-4-20250514", description="LiteLLM model identifier for the default LLM.")
    api_key_env: str = Field(default="ANTHROPIC_API_KEY", description="Environment variable name holding the API key.")


class SignalConfig(BaseModel):
    """Top-level Signal instance configuration.

    Serialized as ``config.yaml`` inside the ``.signal/`` instance directory.
    """
    model_config = ConfigDict(extra="forbid")

    profile_name: str = Field(description="Name or path of the profile to load.")
    ai: AIConfig = Field(default_factory=AIConfig, description="AI layer settings.")
    tools: ToolConfig = Field(default_factory=ToolConfig, description="Global tool execution settings.")

    def to_yaml(self, path: Path) -> None:
        """Serialize this config to a YAML file.

        Args:
            path: Destination file path. Parent directories are created
                if they don't exist.
        """
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
    """Load a SignalConfig from a YAML file.

    Args:
        path: Path to the ``config.yaml`` file.

    Returns:
        Parsed SignalConfig instance.

    Raises:
        ConfigError: If the file does not exist.
    """
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return SignalConfig(**data)


def load_profile(name_or_path: str) -> Profile:
    """Load a profile by name (built-in) or by file path.

    Resolution order:
    1. If ``name_or_path`` is an existing ``.yaml``/``.yml`` file, load it.
    2. Otherwise look for a built-in profile under ``signalagent/profiles/``.

    Args:
        name_or_path: Profile name (e.g. ``"default"``) or file path.

    Returns:
        Parsed Profile instance.

    Raises:
        ConfigError: If the profile cannot be found by either strategy.
    """
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
    """Create a new Signal instance directory with config and subdirectories.

    Args:
        instance_dir: Path to the ``.signal/`` directory to create.
        profile_name: Profile name to store in the generated config.

    Raises:
        InstanceError: If ``instance_dir`` already exists.
    """
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
    """Find a Signal instance directory by searching from start_dir upward.

    Walks parent directories looking for a ``.signal/`` folder that
    contains a ``config.yaml`` file.

    Args:
        start_dir: Directory to begin the search from.

    Returns:
        Path to the ``.signal/`` instance directory.

    Raises:
        InstanceError: If no instance is found up to the filesystem root.
    """
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
