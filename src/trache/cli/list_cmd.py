"""List subcommands: show, create, rename, archive."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape
from rich.table import Table

from trache.cli._context import get_client_and_config, resolve_cache_dir
from trache.cli._errors import handle_resolve_errors
from trache.cli._output import get_output

list_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    return resolve_cache_dir()


@list_app.command("show")
def show_lists() -> None:
    """List all board lists (reads local index, no API call)."""
    from trache.cache.db import load_cards_index, read_lists

    out = get_output()
    cache_dir = _cache_dir()
    lists_index = read_lists(cache_dir)
    cards_index = load_cards_index(cache_dir)

    if not lists_index:
        if out.is_human:
            out.human("[dim]No lists found. Run `trache pull` first.[/dim]")
            raise typer.Exit(1)
        else:
            out.tsv([], header=["name", "card_count"])
            return

    # Count cards per list
    cards_per_list: dict[str, int] = {}
    for _card_id, info in cards_index.items():
        lid = info.get("list_id", "")
        cards_per_list[lid] = cards_per_list.get(lid, 0) + 1

    # Sort by position
    sorted_lists = sorted(lists_index.items(), key=lambda x: x[1].get("pos", 0))

    if out.is_human:
        table = Table(show_header=True, header_style="bold")
        table.add_column("List", style="cyan")
        table.add_column("Cards", justify="right")

        for list_id, info in sorted_lists:
            count = cards_per_list.get(list_id, 0)
            table.add_row(info["name"], str(count))

        out.human_table(table)
    else:
        rows = []
        for list_id, info in sorted_lists:
            count = cards_per_list.get(list_id, 0)
            rows.append([info["name"], str(count)])
        out.tsv(rows, header=["name", "card_count"])


@list_app.command("create")
def create(
    name: str = typer.Argument(help="Name for the new list"),
    pos: str = typer.Option("bottom", "--pos", "-p", help="Position: top or bottom"),
) -> None:
    """Create a new list on the board (API-direct)."""
    from trache.cache.db import add_list

    out = get_output()
    cache_dir = _cache_dir()
    client, config = get_client_and_config(cache_dir)
    with client:
        trello_list = client.create_list(config.board_id, name, pos=pos)

    add_list(trello_list.id, trello_list.name, trello_list.pos, cache_dir)
    if out.is_human:
        out.human(
            f"[green]Created list: {escape(trello_list.name)} (API — available immediately)[/green]"
        )
    else:
        out.json({"ok": True, "id": trello_list.id, "name": trello_list.name})


@list_app.command("rename")
@handle_resolve_errors
def rename(
    identifier: str = typer.Argument(help="List name or ID"),
    new_name: str = typer.Argument(help="New name for the list"),
) -> None:
    """Rename a list (API-direct)."""
    from trache.cache.db import resolve_list_id, update_list

    out = get_output()
    cache_dir = _cache_dir()
    list_id = resolve_list_id(identifier, cache_dir)

    client, _config = get_client_and_config(cache_dir)
    with client:
        trello_list = client.rename_list(list_id, new_name)

    update_list(trello_list.id, trello_list.name, trello_list.pos, cache_dir)
    if out.is_human:
        out.human(
            f"[green]Renamed list → {escape(trello_list.name)} (API — available immediately)[/green]"
        )
    else:
        out.json({"ok": True, "id": trello_list.id, "name": trello_list.name})


@list_app.command("archive")
@handle_resolve_errors
def archive(
    identifier: str = typer.Argument(help="List name or ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm archiving"),
) -> None:
    """Archive (close) a list (API-direct). Requires --yes flag."""
    from trache.cache.db import remove_list, resolve_list_id, resolve_list_name

    out = get_output()

    if not yes:
        out.error("Archiving a list is destructive. Pass --yes to confirm.")
        raise typer.Exit(1)

    cache_dir = _cache_dir()
    list_id = resolve_list_id(identifier, cache_dir)
    list_name = resolve_list_name(list_id, cache_dir)

    client, _config = get_client_and_config(cache_dir)
    with client:
        client.archive_list(list_id)

    remove_list(list_id, cache_dir)
    if out.is_human:
        out.human("[green]Archived list (API — effective immediately)[/green]")
    else:
        out.json({"ok": True, "id": list_id, "name": list_name})
