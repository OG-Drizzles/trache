"""List subcommands: list board lists."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

list_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


@list_app.command("show")
def show_lists() -> None:
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

    table = Table(show_header=True, header_style="bold")
    table.add_column("List", style="cyan")
    table.add_column("Cards", justify="right")

    for list_id, info in sorted_lists:
        count = cards_per_list.get(list_id, 0)
        table.add_row(info["name"], str(count))

    console.print(table)
