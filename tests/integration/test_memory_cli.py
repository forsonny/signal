"""Integration tests for Signal memory CLI commands."""

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.core.types import MemoryType
from signalagent.memory.engine import MemoryEngine

runner = CliRunner()


def _store_test_memory(instance_dir: Path, **overrides):
    """Helper: store a memory and return the Memory object."""
    async def _inner():
        engine = MemoryEngine(instance_dir)
        await engine.initialize()
        try:
            defaults = dict(
                agent="prime",
                memory_type=MemoryType.IDENTITY,
                tags=["python", "testing"],
                content="Test memory content.",
            )
            defaults.update(overrides)
            mem = engine.create_memory(**defaults)
            await engine.store(mem)
            return mem
        finally:
            await engine.close()
    return asyncio.run(_inner())


class TestMemorySearch:
    def test_search_returns_table(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        _store_test_memory(tmp_path / ".signal")

        result = runner.invoke(app, ["memory", "search"])
        assert result.exit_code == 0
        assert "prime" in result.stdout
        assert "identity" in result.stdout

    def test_search_no_results(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["memory", "search", "--tags", "nonexistent"])
        assert result.exit_code == 0
        assert "No memories found" in result.stdout

    def test_search_with_tags(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        _store_test_memory(
            tmp_path / ".signal", tags=["python", "errors"],
        )
        _store_test_memory(
            tmp_path / ".signal", tags=["javascript"],
        )

        result = runner.invoke(app, ["memory", "search", "--tags", "python"])
        assert result.exit_code == 0
        assert "python" in result.stdout

    def test_search_with_comma_separated_tags(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        _store_test_memory(
            tmp_path / ".signal",
            tags=["python", "errors", "testing"],
        )

        result = runner.invoke(
            app, ["memory", "search", "--tags", "python, errors"],
        )
        assert result.exit_code == 0
        assert "python" in result.stdout

    def test_search_no_instance(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["memory", "search"])
        assert result.exit_code == 1
        assert "no signal instance" in result.stdout.lower()


class TestMemoryInspect:
    def test_inspect_shows_memory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        mem = _store_test_memory(tmp_path / ".signal")

        result = runner.invoke(app, ["memory", "inspect", mem.id])
        assert result.exit_code == 0
        assert mem.id in result.stdout
        assert "Test memory content" in result.stdout

    def test_inspect_shows_metadata(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        mem = _store_test_memory(tmp_path / ".signal")

        result = runner.invoke(app, ["memory", "inspect", mem.id])
        assert result.exit_code == 0
        assert "prime" in result.stdout
        assert "identity" in result.stdout
        assert "0.50" in result.stdout

    def test_inspect_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["memory", "inspect", "mem_nonexist"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_inspect_no_instance(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["memory", "inspect", "mem_12345678"])
        assert result.exit_code == 1
        assert "no signal instance" in result.stdout.lower()
