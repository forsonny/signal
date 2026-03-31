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
