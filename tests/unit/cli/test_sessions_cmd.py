"""Integration tests for signal sessions CLI commands."""
import pytest
from datetime import datetime, timezone

from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.core.models import Turn
from signalagent.sessions.manager import SessionManager


runner = CliRunner()


class TestSessionsList:
    def test_sessions_list_no_instance(self, tmp_path, monkeypatch):
        """signal sessions list exits 1 when no instance found."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 1

    def test_sessions_list_empty(self, tmp_path, monkeypatch):
        """signal sessions list shows message when no sessions exist."""
        instance_dir = tmp_path / ".signal"
        instance_dir.mkdir()
        (instance_dir / "config.yaml").write_text("profile_name: blank\n")
        (instance_dir / "data" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0
        assert "No sessions" in result.output

    def test_sessions_list_shows_sessions(self, tmp_path, monkeypatch):
        """signal sessions list displays session table."""
        instance_dir = tmp_path / ".signal"
        instance_dir.mkdir()
        (instance_dir / "config.yaml").write_text("profile_name: blank\n")
        sessions_dir = instance_dir / "data" / "sessions"
        sessions_dir.mkdir(parents=True)

        sm = SessionManager(sessions_dir)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="hello world", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="hi there", timestamp=now))

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0
        assert sid in result.output
        assert "hello world" in result.output
