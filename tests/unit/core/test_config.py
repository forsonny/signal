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

    def test_finds_in_parent_dir(self, tmp_path):
        instance_dir = tmp_path / ".signal"
        create_instance(instance_dir, "blank")

        child_dir = tmp_path / "sub" / "deep" / "nested"
        child_dir.mkdir(parents=True)

        found = find_instance(child_dir)
        assert found == instance_dir

    def test_raises_if_not_found(self, tmp_path):
        import pytest
        with pytest.raises(InstanceError, match="No Signal instance found"):
            find_instance(tmp_path)
