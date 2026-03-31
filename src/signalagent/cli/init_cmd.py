"""signal init -- create a new Signal instance."""

from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.config import create_instance, load_profile
from signalagent.core.errors import ConfigError, InstanceError

console = Console()


@app.command()
def init(
    profile: str = typer.Option("blank", help="Profile to initialize with"),
) -> None:
    """Initialize a new Signal instance in the current directory."""
    instance_dir = Path.cwd() / ".signal"

    try:
        load_profile(profile)
    except ConfigError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    try:
        create_instance(instance_dir, profile)
    except InstanceError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]Signal instance initialized with profile '{profile}'[/green]"
    )
