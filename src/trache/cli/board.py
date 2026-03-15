"""Board management subcommands: list, switch, offboard."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trache.cli._context import (
    TRACHE_ROOT,
    get_active_board_name,
    list_board_names,
    set_active_board,
)

board_app = typer.Typer(no_args_is_help=True)
console = Console()


@board_app.command("list")
def list_boards() -> None:
    """List all configured boards."""
    from trache.config import SyncState, TracheConfig

    boards = list_board_names()
    if not boards:
        console.print("[dim]No boards configured. Run 'trache init' first.[/dim]")
        return

    try:
        active = get_active_board_name()
    except FileNotFoundError:
        active = None

    table = Table(show_header=True, header_style="bold")
    table.add_column("", width=2)
    table.add_column("Alias", style="cyan")
    table.add_column("Trello Board")
    table.add_column("Last Pull")

    for alias in boards:
        board_dir = TRACHE_ROOT / "boards" / alias
        marker = "*" if alias == active else ""

        # Load board name from config
        trello_name = ""
        try:
            config = TracheConfig.load(board_dir)
            trello_name = config.board_name or config.board_id[:12]
        except Exception:
            trello_name = "(config error)"

        # Load last pull from state
        last_pull = ""
        try:
            state = SyncState.load(board_dir)
            if state.last_pull:
                last_pull = state.last_pull[:16].replace("T", " ")
        except Exception:
            pass

        table.add_row(marker, alias, trello_name, last_pull)

    console.print(table)


@board_app.command("switch")
def switch(
    alias: str = typer.Argument(help="Board alias to switch to"),
) -> None:
    """Switch the active board."""
    boards = list_board_names()
    if alias not in boards:
        console.print(f"[red]Board '{alias}' not found.[/red]")
        if boards:
            console.print(f"Available boards: {', '.join(boards)}")
        raise typer.Exit(1)

    set_active_board(alias)
    console.print(f"[green]Switched to board: {alias}[/green]")


@board_app.command("offboard")
def offboard(
    alias: str = typer.Argument(help="Board alias to offboard"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm offboarding"),
    archive: bool = typer.Option(
        False, "--archive", help="Also archive the board on Trello"
    ),
    force: bool = typer.Option(
        False, "--force", help="Offboard even if there are unpushed changes"
    ),
) -> None:
    """Remove a board's local cache. Requires --yes flag."""
    if not yes:
        console.print(
            "[red]Offboarding a board removes all local data. Pass --yes to confirm.[/red]"
        )
        raise typer.Exit(1)

    boards = list_board_names()
    if alias not in boards:
        console.print(f"[red]Board '{alias}' not found.[/red]")
        raise typer.Exit(1)

    board_dir = TRACHE_ROOT / "boards" / alias

    # Dirty guard
    if not force:
        from trache.cache.diff import compute_diff

        try:
            changeset = compute_diff(board_dir)
            if not changeset.is_empty:
                console.print(
                    f"[red]Board '{alias}' has unpushed changes. "
                    f"Use --force to destroy anyway.[/red]"
                )
                raise typer.Exit(1)
        except (SystemExit, typer.Exit):
            raise
        except Exception:
            pass  # If diff fails (e.g. no cards), proceed

    # Archive on Trello if requested
    if archive:
        from trache.cli._context import get_client_and_config

        try:
            client, config = get_client_and_config(board_dir)
            with client:
                client.close_board(config.board_id)
            console.print(f"[green]Archived board on Trello[/green]")
        except Exception as e:
            console.print(f"[red]Failed to archive on Trello: {e}[/red]")
            raise typer.Exit(1)

    # Validate path is under .trache/boards/ before removing
    resolved = board_dir.resolve()
    boards_root = (TRACHE_ROOT / "boards").resolve()
    if not resolved.is_relative_to(boards_root):
        console.print("[red]Safety check failed: path is not under .trache/boards/[/red]")
        raise typer.Exit(1)

    shutil.rmtree(board_dir)

    # Update active board if needed
    try:
        active = get_active_board_name()
    except FileNotFoundError:
        active = None

    if active == alias:
        remaining = list_board_names()
        if remaining:
            set_active_board(remaining[0])
            console.print(f"Switched active board to: {remaining[0]}")
        else:
            active_file = TRACHE_ROOT / "active"
            if active_file.exists():
                active_file.unlink()

    console.print(f"[green]Offboarded board: {alias}[/green]")
