"""Typer app root: init, pull, push, sync, status, diff."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from trache import __version__
from trache.cli.card import card_app
from trache.cli.checklist import checklist_app
from trache.cli.comment import comment_app

app = typer.Typer(
    name="trache",
    help="Local-first Trello cache with Git-style sync, optimised for AI-agent workflows.",
    no_args_is_help=True,
)
app.add_typer(card_app, name="card", help="Card operations")
app.add_typer(checklist_app, name="checklist", help="Checklist operations")
app.add_typer(comment_app, name="comment", help="Comment operations")

console = Console()


def _get_client():
    """Create an authenticated Trello client from config."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.config import TracheConfig

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    return TrelloClient(auth), config


@app.command()
def init(
    board_id: str = typer.Option(None, "--board-id", "-b", help="Trello board ID"),
    board_url: str = typer.Option(None, "--board-url", "-u", help="Trello board URL"),
) -> None:
    """Initialise Trache cache for a board."""
    from trache.config import TracheConfig, ensure_cache_structure

    if not board_id and not board_url:
        board_id = typer.prompt("Board ID")

    if board_url and not board_id:
        # Extract board ID from URL: https://trello.com/b/<shortLink>/...
        parts = board_url.rstrip("/").split("/")
        try:
            b_idx = parts.index("b")
            board_id = parts[b_idx + 1]
        except (ValueError, IndexError):
            console.print("[red]Could not extract board ID from URL[/red]")
            raise typer.Exit(1)

    cache_dir = Path(".trache")
    if cache_dir.exists():
        console.print("[yellow].trache/ already exists. Re-initialising config.[/yellow]")

    config = TracheConfig(board_id=board_id)

    # Try to fetch board name if auth is available
    try:
        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
        with TrelloClient(auth) as client:
            board = client.get_board(board_id)
            config.board_name = board.name
            console.print(f"Board: [bold]{board.name}[/bold]")
    except Exception:
        console.print(
            "[yellow]Could not fetch board name (auth not configured or offline)[/yellow]"
        )

    ensure_cache_structure(cache_dir)
    config.save(cache_dir)
    console.print(f"[green]Initialised .trache/ for board {board_id}[/green]")

    from trache.cli.agents import print_init_agent_guidance

    print_init_agent_guidance()


@app.command()
def pull(
    card: Optional[str] = typer.Option(None, "--card", "-c", help="Pull single card (ID or UID6)"),
    list_name: Optional[str] = typer.Option(
        None, "--list", "-l", help="Pull all cards in list (ID or name)"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite dirty working state"),
) -> None:
    """Pull data from Trello into local cache."""
    from trache.sync.pull import pull_card, pull_full_board, pull_list

    client, config = _get_client()
    cache_dir = Path(".trache")

    try:
        with client:
            if card:
                result = pull_card(card, config, client, cache_dir, force=force)
                console.print(f"[green]Pulled card: {result.title} [{result.uid6}][/green]")
            elif list_name:
                cards = pull_list(list_name, config, client, cache_dir, force=force)
                console.print(f"[green]Pulled {len(cards)} cards from list[/green]")
            else:
                count = pull_full_board(config, client, cache_dir, force=force)
                console.print(f"[green]Pulled {count} cards[/green]")
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except KeyError as e:
        msg = e.args[0] if e.args else "Requested item not found"
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show dirty state summary (modified/added/deleted)."""
    from trache.cache.diff import compute_diff

    cache_dir = Path(".trache")
    changeset = compute_diff(cache_dir)

    if changeset.is_empty:
        console.print("Clean — no local changes.")
        return

    if changeset.added:
        console.print(f"[green]  Added: {len(changeset.added)}[/green]")
        for c in changeset.added:
            console.print(f"    + {c.title}")

    if changeset.modified:
        console.print(f"[yellow]  Modified: {len(changeset.modified)}[/yellow]")
        for c in changeset.modified:
            fields = ", ".join(c.field_changes.keys())
            console.print(f"    ~ {c.title} ({fields})")

    if changeset.deleted:
        console.print(f"[red]  Deleted: {len(changeset.deleted)}[/red]")
        for c in changeset.deleted:
            console.print(f"    - {c.title}")


@app.command()
def diff() -> None:
    """Show detailed diff between clean and working copy."""
    from trache.cache.diff import compute_diff, format_diff

    cache_dir = Path(".trache")
    changeset = compute_diff(cache_dir)
    console.print(format_diff(changeset))


@app.command()
def push(
    card: Optional[str] = typer.Option(None, "--card", "-c", help="Push single card (ID or UID6)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be pushed without pushing"
    ),
) -> None:
    """Push local changes to Trello."""
    from trache.sync.push import push_changes

    client, config = _get_client()
    cache_dir = Path(".trache")

    with client:
        changeset, result = push_changes(
            config, client, cache_dir, dry_run=dry_run, card_filter=card
        )

    if dry_run:
        console.print("[yellow]Dry run — no changes pushed[/yellow]")

    if changeset.is_empty:
        console.print("Nothing to push.")
        return

    if result.pushed:
        console.print(f"[green]Pushed: {len(result.pushed)}[/green]")
    if result.created:
        console.print(f"[green]Created: {len(result.created)}[/green]")
    if result.archived:
        console.print(f"[yellow]Archived: {len(result.archived)}[/yellow]")
    if result.errors:
        for err in result.errors:
            console.print(f"[red]Error: {err}[/red]")


@app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced"),
) -> None:
    """Push local changes then pull latest from Trello."""
    from trache.sync.pull import pull_full_board
    from trache.sync.push import push_changes

    client, config = _get_client()
    cache_dir = Path(".trache")

    with client:
        # Push first
        changeset, result = push_changes(config, client, cache_dir, dry_run=dry_run)
        if not changeset.is_empty:
            console.print(f"Pushed {result.total} changes")
            if result.errors:
                for err in result.errors:
                    console.print(f"[red]Error: {err}[/red]")
                console.print(
                    "[red]Push had errors — skipping full pull to preserve local state[/red]"
                )
                raise typer.Exit(1)

        # Only full pull if no errors
        if not dry_run:
            count = pull_full_board(config, client, cache_dir, force=True)
            console.print(f"[green]Pulled {count} cards[/green]")
        else:
            console.print("[yellow]Dry run — skipping pull[/yellow]")


@app.command()
def agents(
    reference: bool = typer.Option(
        False, "--reference", help="Print on-demand command/workflow reference"
    ),
) -> None:
    """Print AI agent setup instructions or command reference."""
    from trache.cli.agents import print_install_block, print_reference_block

    if reference:
        print_reference_block()
    else:
        print_install_block()


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"trache {__version__}")


if __name__ == "__main__":
    app()
