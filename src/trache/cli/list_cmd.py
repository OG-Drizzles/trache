"""List subcommands: show, create, rename, archive."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from trache.cli._errors import handle_resolve_errors

list_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


def _get_client_and_config():
    """Create an authenticated Trello client from config."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.config import TracheConfig

    config = TracheConfig.load(_cache_dir())
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    return TrelloClient(auth), config


@list_app.command("show")
def show_lists(
    raw: bool = typer.Option(False, "--raw", help="Tab-separated output"),
) -> None:
    """List all board lists (reads local index, no API call)."""
    from trache.cache.index import load_index

    index_dir = _cache_dir() / "indexes"
    lists_index = load_index(index_dir, "lists_by_id")
    cards_index = load_index(index_dir, "cards_by_id")

    if not lists_index:
        console.print("[dim]No lists found. Run `trache pull` first.[/dim]")
        raise typer.Exit(1)

    # Count cards per list
    cards_per_list: dict[str, int] = {}
    for _card_id, info in cards_index.items():
        lid = info.get("list_id", "")
        cards_per_list[lid] = cards_per_list.get(lid, 0) + 1

    # Sort by position
    sorted_lists = sorted(lists_index.items(), key=lambda x: x[1].get("pos", 0))

    if raw:
        for list_id, info in sorted_lists:
            count = cards_per_list.get(list_id, 0)
            print(f"{info['name']}\t{count}")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("List", style="cyan")
    table.add_column("Cards", justify="right")

    for list_id, info in sorted_lists:
        count = cards_per_list.get(list_id, 0)
        table.add_row(info["name"], str(count))

    console.print(table)


@list_app.command("create")
def create(
    name: str = typer.Argument(help="Name for the new list"),
    pos: str = typer.Option("bottom", "--pos", "-p", help="Position: top or bottom"),
) -> None:
    """Create a new list on the board (API-direct)."""
    from trache.cache.index import add_list_to_index

    client, config = _get_client_and_config()
    with client:
        trello_list = client.create_list(config.board_id, name, pos=pos)

    add_list_to_index(trello_list.id, trello_list.name, trello_list.pos, _cache_dir() / "indexes")
    console.print(
        f"[green]Created list: {escape(trello_list.name)} (API — available immediately)[/green]"
    )


@list_app.command("rename")
@handle_resolve_errors
def rename(
    identifier: str = typer.Argument(help="List name or ID"),
    new_name: str = typer.Argument(help="New name for the list"),
) -> None:
    """Rename a list (API-direct)."""
    from trache.cache.index import resolve_list_id, update_list_in_index

    index_dir = _cache_dir() / "indexes"
    list_id = resolve_list_id(identifier, index_dir)

    client, _config = _get_client_and_config()
    with client:
        trello_list = client.rename_list(list_id, new_name)

    update_list_in_index(trello_list.id, trello_list.name, trello_list.pos, index_dir)
    console.print(
        f"[green]Renamed list → {escape(trello_list.name)} (API — available immediately)[/green]"
    )


@list_app.command("archive")
@handle_resolve_errors
def archive(
    identifier: str = typer.Argument(help="List name or ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm archiving"),
) -> None:
    """Archive (close) a list (API-direct). Requires --yes flag."""
    from trache.cache.index import remove_list_from_index, resolve_list_id

    if not yes:
        console.print(
            "[red]Archiving a list is destructive. Pass --yes to confirm.[/red]"
        )
        raise typer.Exit(1)

    index_dir = _cache_dir() / "indexes"
    list_id = resolve_list_id(identifier, index_dir)

    client, _config = _get_client_and_config()
    with client:
        client.archive_list(list_id)

    remove_list_from_index(list_id, index_dir)
    console.print(
        f"[green]Archived list (API — effective immediately)[/green]"
    )
