"""signal memory -- search and inspect agent memories."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signalagent.core.errors import InstanceError

console = Console()

memory_app = typer.Typer(
    name="memory",
    help="Search and inspect agent memories.",
    no_args_is_help=True,
)


@memory_app.command("search")
def search_cmd(
    tags: str = typer.Option(None, help="Comma-separated tags to filter by"),
    agent: str = typer.Option(None, help="Filter by agent name"),
    memory_type: str = typer.Option(None, "--type", help="Filter by memory type"),
    limit: int = typer.Option(10, help="Maximum results to return"),
) -> None:
    """Search memories by tags, agent, and type.

    Args:
        tags: Comma-separated list of tags to filter by.
        agent: Agent name to filter results.
        memory_type: Memory type filter (e.g. ``"learned"``).
        limit: Maximum number of results to display.

    Raises:
        typer.Exit: If no Signal instance is found.
    """
    try:
        from signalagent.core.config import find_instance  # deferred: heavyweight

        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print(
            "[red]No Signal instance found. Run 'signal init' first.[/red]"
        )
        raise typer.Exit(1)

    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    results = asyncio.run(
        _async_search(instance_dir, tag_list, agent, memory_type, limit)
    )

    if not results:
        console.print("No memories found.")
        return

    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Agent")
    table.add_column("Type")
    table.add_column("Tags")
    table.add_column("Confidence", justify="right")
    table.add_column("Updated")

    for mem in results:
        table.add_row(
            mem.id,
            mem.agent,
            mem.type.value,
            ", ".join(mem.tags),
            f"{mem.confidence:.2f}",
            mem.updated.strftime("%Y-%m-%d"),
        )

    console.print(table)


async def _async_search(
    instance_dir: Path,
    tags: list[str] | None,
    agent: str | None,
    memory_type: str | None,
    limit: int,
) -> list:
    """Async bridge for search -- deferred imports keep CLI startup fast.

    Args:
        instance_dir: Path to the ``.signal/`` instance directory.
        tags: Optional tag filter.
        agent: Optional agent-name filter.
        memory_type: Optional memory-type filter.
        limit: Maximum number of results.

    Returns:
        List of ``Memory`` objects matching the criteria.
    """
    from signalagent.memory.engine import MemoryEngine  # deferred: pulls in aiosqlite

    engine = MemoryEngine(instance_dir)
    await engine.initialize()
    try:
        return await engine.search(
            tags=tags, agent=agent, memory_type=memory_type, limit=limit,
        )
    finally:
        await engine.close()


@memory_app.command("inspect")
def inspect_cmd(
    memory_id: str = typer.Argument(..., help="Memory ID to inspect"),
) -> None:
    """Inspect a specific memory by ID.

    Args:
        memory_id: The unique memory identifier to look up.

    Raises:
        typer.Exit: If no instance is found or the memory does not exist.
    """
    try:
        from signalagent.core.config import find_instance  # deferred: heavyweight

        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print(
            "[red]No Signal instance found. Run 'signal init' first.[/red]"
        )
        raise typer.Exit(1)

    memory = asyncio.run(_async_inspect(instance_dir, memory_id))

    if memory is None:
        console.print(f"[red]Memory not found: {memory_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{memory.id}[/bold cyan]")
    console.print(f"Agent:        {memory.agent}")
    console.print(f"Type:         {memory.type.value}")
    console.print(f"Tags:         {', '.join(memory.tags)}")
    console.print(f"Confidence:   {memory.confidence:.2f}")
    console.print(f"Version:      {memory.version}")
    console.print(f"Created:      {memory.created.isoformat()}")
    console.print(f"Updated:      {memory.updated.isoformat()}")
    console.print(f"Accessed:     {memory.accessed.isoformat()}")
    console.print(f"Access count: {memory.access_count}")
    if memory.changelog:
        console.print("Changelog:")
        for entry in memory.changelog:
            console.print(f"  {entry}")
    console.print()
    console.print(memory.content)


async def _async_inspect(instance_dir: Path, memory_id: str):
    """Async bridge for inspect -- deferred imports keep CLI startup fast.

    Args:
        instance_dir: Path to the ``.signal/`` instance directory.
        memory_id: The unique memory identifier to look up.

    Returns:
        A ``Memory`` object, or ``None`` if not found.
    """
    from signalagent.memory.engine import MemoryEngine  # deferred: pulls in aiosqlite

    engine = MemoryEngine(instance_dir)
    await engine.initialize()
    try:
        return await engine.inspect(memory_id)
    finally:
        await engine.close()
