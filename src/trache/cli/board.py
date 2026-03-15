"""Board management subcommands: list, switch, offboard."""

from __future__ import annotations

import shutil

import typer
from rich.table import Table

from trache.cli._context import (
    TRACHE_ROOT,
    get_active_board_name,
    list_board_names,
    set_active_board,
)
from trache.cli._output import get_output

board_app = typer.Typer(no_args_is_help=True)


@board_app.command("list")
def list_boards() -> None:
    """List all configured boards."""
    from trache.config import SyncState, TracheConfig

    out = get_output()
    boards = list_board_names()
    if not boards:
        if out.is_human:
            out.human("[dim]No boards configured. Run 'trache init' first.[/dim]")
        else:
            out.tsv([], header=["alias", "board_name", "last_pull", "active"])
        return

    try:
        active = get_active_board_name()
    except FileNotFoundError:
        active = None

    if out.is_human:
        table = Table(show_header=True, header_style="bold")
        table.add_column("", width=2)
        table.add_column("Alias", style="cyan")
        table.add_column("Trello Board")
        table.add_column("Last Pull")

        for alias in boards:
            board_dir = TRACHE_ROOT / "boards" / alias
            marker = "*" if alias == active else ""

            trello_name = ""
            try:
                config = TracheConfig.load(board_dir)
                trello_name = config.board_name or config.board_id[:12]
            except Exception:
                trello_name = "(config error)"

            last_pull = ""
            try:
                state = SyncState.load(board_dir)
                if state.last_pull:
                    last_pull = state.last_pull[:16].replace("T", " ")
            except Exception:
                pass

            table.add_row(marker, alias, trello_name, last_pull)

        out.human_table(table)
    else:
        rows = []
        for alias in boards:
            board_dir = TRACHE_ROOT / "boards" / alias
            is_active = alias == active

            trello_name = ""
            try:
                config = TracheConfig.load(board_dir)
                trello_name = config.board_name or config.board_id[:12]
            except Exception:
                trello_name = "(config error)"

            last_pull = ""
            try:
                state = SyncState.load(board_dir)
                if state.last_pull:
                    last_pull = state.last_pull[:16].replace("T", " ")
            except Exception:
                pass

            rows.append([alias, trello_name, last_pull, str(is_active).lower()])

        out.tsv(rows, header=["alias", "board_name", "last_pull", "active"])


@board_app.command("switch")
def switch(
    alias: str = typer.Argument(help="Board alias to switch to"),
) -> None:
    """Switch the active board."""
    out = get_output()
    boards = list_board_names()
    if alias not in boards:
        out.error(f"Board '{alias}' not found.", available_boards=boards)
        if out.is_human and boards:
            out.human(f"Available boards: {', '.join(boards)}")
        raise typer.Exit(1)

    set_active_board(alias)
    if out.is_human:
        out.human(f"[green]Switched to board: {alias}[/green]")
    else:
        out.json({"ok": True, "alias": alias})


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
    out = get_output()

    if not yes:
        out.error("Offboarding a board removes all local data. Pass --yes to confirm.")
        raise typer.Exit(1)

    boards = list_board_names()
    if alias not in boards:
        out.error(f"Board '{alias}' not found.")
        raise typer.Exit(1)

    board_dir = TRACHE_ROOT / "boards" / alias

    # Dirty guard
    if not force:
        from trache.cache.diff import compute_diff

        try:
            changeset = compute_diff(board_dir)
            if not changeset.is_empty:
                out.error(
                    f"Board '{alias}' has unpushed changes. "
                    f"Use --force to destroy anyway."
                )
                raise typer.Exit(1)
        except (SystemExit, typer.Exit):
            raise
        except Exception:
            pass  # If diff fails (e.g. no cards), proceed

    # Archive on Trello if requested
    archived_on_trello = False
    if archive:
        from trache.cli._context import get_client_and_config

        try:
            client, config = get_client_and_config(board_dir)
            with client:
                client.close_board(config.board_id)
            archived_on_trello = True
            out.human("[green]Archived board on Trello[/green]")
        except Exception as e:
            out.error(f"Failed to archive on Trello: {e}")
            raise typer.Exit(1)

    # Validate path is under .trache/boards/ before removing
    resolved = board_dir.resolve()
    boards_root = (TRACHE_ROOT / "boards").resolve()
    if not resolved.is_relative_to(boards_root):
        out.error("Safety check failed: path is not under .trache/boards/")
        raise typer.Exit(1)

    shutil.rmtree(board_dir)

    # Update active board if needed
    try:
        active = get_active_board_name()
    except FileNotFoundError:
        active = None

    new_active_board = None
    if active == alias:
        remaining = list_board_names()
        if remaining:
            new_active_board = remaining[0]
            set_active_board(new_active_board)
            out.human(f"Switched active board to: {new_active_board}")
        else:
            active_file = TRACHE_ROOT / "active"
            if active_file.exists():
                active_file.unlink()

    if out.is_human:
        out.human(f"[green]Offboarded board: {alias}[/green]")
    else:
        out.json({
            "ok": True,
            "alias": alias,
            "archived_on_trello": archived_on_trello,
            "new_active_board": new_active_board,
        })
