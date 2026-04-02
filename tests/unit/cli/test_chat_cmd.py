"""Integration tests for signal chat CLI command."""
import pytest

from typer.testing import CliRunner

from signalagent.cli.app import app


runner = CliRunner()


class TestChatCommand:
    def test_chat_no_instance_exits_1(self, tmp_path, monkeypatch):
        """signal chat exits 1 when no instance found."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["chat"])
        assert result.exit_code == 1

    def test_chat_accepts_session_option(self):
        """signal chat --session is a recognized option."""
        result = runner.invoke(app, ["chat", "--session", "ses_test0001"])
        assert "No such option" not in (result.output or "")
