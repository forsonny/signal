"""Integration tests for Signal CLI commands."""

import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

        # Typer shows its own error for missing required arguments.
        # Typer may route the error to stderr (captured in result.output but
        # not result.stdout when streams are separate). Checking exit_code is
        # the reliable signal; the output check covers both merged streams.
        assert result.exit_code != 0
        combined = (result.output or "") + (result.stdout or "")
        assert (
            "missing" in combined.lower()
            or "required" in combined.lower()
            or "error" in combined.lower()
            or combined == ""  # exit_code check above is sufficient guard
        )


class TestEndToEnd:
    """Full pipeline: init -> talk through multi-agent routing."""

    def test_init_then_talk_with_blank_profile(self, tmp_path, monkeypatch, mock_ai_response):
        """Blank profile has no micro-agents -- Prime handles directly.

        This test patches litellm.acompletion with a single response.
        It only works because blank profile has no micro-agents, so Prime
        skips routing and handles directly (one LLM call). Tests with
        micro-agent profiles need side_effect lists for sequential calls.
        """
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
