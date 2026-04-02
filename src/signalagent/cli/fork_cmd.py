# src/signalagent/cli/fork_cmd.py
"""signal fork -- run parallel approaches in separate worktrees."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.errors import InstanceError

console = Console()


@app.command()
def fork(
    tasks: List[str] = typer.Argument(..., help="Task descriptions (one per branch, minimum 2)"),
    concurrency: int = typer.Option(
        0, "--concurrency", "-c",
        help="Max concurrent branches (0 = use profile default)",
    ),
) -> None:
    """Run multiple approaches in parallel worktrees."""
    if len(tasks) < 2:
        console.print("[red]At least 2 task descriptions required for forking.[/red]")
        raise typer.Exit(1)

    try:
        from signalagent.core.config import find_instance
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    results = asyncio.run(_async_fork(tasks, instance_dir, concurrency))

    any_success = any(r.success for r in results)
    console.print(f"\nFork complete: {len(results)} branches\n")

    for r in results:
        console.print(f'--- Branch {r.branch_index + 1}: "{r.task_description}" ---')
        if r.success:
            console.print("Status: [green]Success[/green]")
            preview = r.response[:200] + ("..." if len(r.response) > 200 else "")
            console.print(f"Response: {preview}")
            console.print(f"Changed files: {len(r.changed_files)}")
            if r.worktree_id:
                console.print(f"Worktree: {r.worktree_id}")
        else:
            console.print("Status: [red]Failed[/red]")
            console.print(f"Error: {r.error}")
        console.print()

    console.print("Review with: signal worktree list")
    console.print("Merge winner: signal worktree merge <id>")
    console.print("Discard rest: signal worktree discard <id>")

    raise typer.Exit(0 if any_success else 1)


async def _async_fork(
    tasks: list[str], instance_dir: Path, concurrency: int,
) -> list:
    """Async implementation -- deferred imports keep CLI startup fast."""
    from signalagent.core.config import load_config, load_profile
    from signalagent.runtime.bootstrap import bootstrap
    from signalagent.worktrees.fork import ForkRunner
    from signalagent.worktrees.manifest import WorktreeManifest
    from signalagent.worktrees.manager import WorktreeManager

    config = load_config(instance_dir / "config.yaml")
    profile = load_profile(config.profile_name)
    executor, _bus, _host = await bootstrap(instance_dir, config, profile)

    max_concurrent = concurrency if concurrency > 0 else profile.fork.max_concurrent_branches

    # Separate instances from bootstrap's -- works because both
    # WorktreeManifest and WorktreeManager are stateless file I/O
    # against the same paths (no in-memory cache, no buffered writes).
    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    manager = WorktreeManager(instance_dir=instance_dir, workspace_root=instance_dir)

    fork_runner = ForkRunner(
        executor=executor,
        manifest=manifest,
        manager=manager,
        max_concurrent=max_concurrent,
    )
    return await fork_runner.run(tasks)
