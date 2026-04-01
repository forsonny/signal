"""Unit tests for bootstrap -- all real objects, only AILayer mocked."""

import pytest
from unittest.mock import AsyncMock

from signalagent.ai.layer import AIResponse
from signalagent.core.config import SignalConfig
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
)
from signalagent.core.types import PRIME_AGENT
from signalagent.runtime.bootstrap import bootstrap


def _make_ai_response(content: str) -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


@pytest.fixture
def config() -> SignalConfig:
    return SignalConfig(profile_name="test")


@pytest.fixture
def profile_with_micros() -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        micro_agents=[
            MicroAgentConfig(
                name="code-review",
                skill="Code quality",
                talks_to=["prime"],
            ),
            MicroAgentConfig(
                name="git",
                skill="Version control",
                talks_to=["prime", "code-review"],
            ),
        ],
    )


@pytest.fixture
def profile_no_micros() -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
    )


class TestBootstrap:
    @pytest.mark.asyncio
    async def test_returns_executor_bus_host(self, tmp_path, config, profile_with_micros, monkeypatch):
        mock_ai_class = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)

        assert executor is not None
        assert bus is not None
        assert host is not None
        assert host.get(PRIME_AGENT) is not None
        assert host.get("code-review") is not None
        assert host.get("git") is not None

    @pytest.mark.asyncio
    async def test_end_to_end_routing(self, tmp_path, config, profile_with_micros, monkeypatch):
        """Full path: executor -> bus -> Prime -> routing -> bus -> micro -> response."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response("code-review"),
                _make_ai_response("Review complete"),
            ]
        )
        mock_ai_class = lambda config: mock_ai
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)
        result = await executor.run("review my code")

        assert result.content == "Review complete"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_micros_prime_handles_directly(self, tmp_path, config, profile_no_micros, monkeypatch):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("I handled it"),
        )
        mock_ai_class = lambda config: mock_ai
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)
        result = await executor.run("hello")

        assert result.content == "I handled it"
        assert mock_ai.complete.call_count == 1
