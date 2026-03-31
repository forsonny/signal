"""signal talk -- send a message to Signal."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.errors import InstanceError

console = Console()


def _run_talk(message: str, instance_dir: Path) -> str:
    """Run the talk pipeline synchronously (wraps async internals)."""
    return asyncio.run(_async_talk(message, instance_dir))


async def _async_talk(message: str, instance_dir: Path) -> str:
    """Async implementation of the talk pipeline.

    Imports are deferred to inside this function to avoid circular imports
    and keep CLI startup fast. The AI layer and executor are heavyweight
    modules that pull in litellm -- deferring their import means 'signal --help'
    and 'signal init' don't pay that cost.
    """
    from signalagent.ai.layer import AILayer  # deferred: heavyweight import
    from signalagent.core.config import load_config, load_profile
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
        from signalagent.core.config import find_instance  # deferred: see _async_talk docstring
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    response = _run_talk(message, instance_dir)
    console.print(response)
