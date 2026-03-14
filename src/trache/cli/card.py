"""Card subcommands: list, show, edit-title, edit-desc, move, create, archive, labels."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from trache.cli._errors import handle_resolve_errors

card_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


def _warn_if_archived(identifier: str) -> None:
    """Print a warning if the card is archived. Does not block the operation."""
    from trache.cache.working import read_working_card

    try:
        card = read_working_card(identifier, _cache_dir())
        if card.closed:
            console.print(
                f"[yellow]Warning: card [{card.uid6}] is archived. "
                f"Editing an archived card may have no effect on Trello.[/yellow]"
            )
    except (KeyError, FileNotFoundError):
        pass  # Card not found — let the actual command handle the error


@card_app.command("list")
@handle_resolve_errors
def list_cards(
    list_name: Optional[str] = typer.Option(
        None, "--list", "-l", help="Filter by list (ID or name)"
    ),
) -> None:
    """List cards from local index (no API call)."""
    from trache.cache.index import load_index, resolve_list_id

    index_dir = _cache_dir() / "indexes"
    cards_index = load_index(index_dir, "cards_by_id")
    lists_index = load_index(index_dir, "lists_by_id")

    # Build list name lookup
    list_names = {lid: info["name"] for lid, info in lists_index.items()}

    # Filter by list if specified
    filter_list_id = None
    if list_name:
        filter_list_id = resolve_list_id(list_name, index_dir)

    table = Table(show_header=True, header_style="bold")
    table.add_column("UID6", style="cyan", width=8)
    table.add_column("List", width=20)
    table.add_column("Title")

    for card_id, info in cards_index.items():
        if filter_list_id and info["list_id"] != filter_list_id:
            continue
        list_display = list_names.get(info["list_id"], info["list_id"][:8])
        table.add_row(info["uid6"], list_display, info["title"])

    console.print(table)


@card_app.command("show")
@handle_resolve_errors
def show_card(
    identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Show a single card (loads one .md file, no API call)."""
    from trache.cache.index import resolve_list_name
    from trache.cache.working import read_working_card

    cache_dir = _cache_dir()
    card = read_working_card(identifier, cache_dir)

    # Title (truncate pathological lengths)
    if len(card.title) > 120:
        title_display = card.title[:120] + f"… (len={len(card.title)})"
    else:
        title_display = card.title
    console.print(f"[bold]{title_display}[/bold]  [{card.uid6}]")

    # List name
    list_name = resolve_list_name(card.list_id, cache_dir / "indexes")
    console.print(f"List: {list_name}")

    # Status line
    status_parts = []
    if card.closed:
        status_parts.append("[red]ARCHIVED[/red]")
    if card.dirty:
        status_parts.append("[yellow]MODIFIED[/yellow]")
    if not status_parts:
        status_parts.append("[green]CLEAN[/green]")
    console.print(f"Status: {' | '.join(status_parts)}")

    if card.labels:
        console.print(f"Labels: {', '.join(card.labels)}")
    if card.due:
        console.print(f"Due: {card.due}")
    console.print()
    if card.description:
        console.print(card.description)
    else:
        console.print("[dim]No description[/dim]")
    if card.checklists:
        console.print()
        for cl in card.checklists:
            console.print(f"[bold]{cl.name}[/bold]: {cl.complete}/{cl.total} complete")
            for item in cl.items:
                check = "[x]" if item.state == "complete" else "[ ]"
                console.print(f"  {check} {item.name} [dim]({item.id})[/dim]")


@card_app.command("edit-title")
@handle_resolve_errors
def edit_title(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    title: str = typer.Argument(help="New title"),
) -> None:
    """Edit card title in working copy."""
    from trache.cache.working import edit_title as _edit_title

    _warn_if_archived(identifier)
    card = _edit_title(identifier, title, _cache_dir())
    console.print(f"[green]Title updated: {card.title} [{card.uid6}][/green]")


@card_app.command("edit-desc")
@handle_resolve_errors
def edit_desc(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    desc: str = typer.Argument(help="New description"),
) -> None:
    """Edit card description in working copy."""
    from trache.cache.working import edit_description

    _warn_if_archived(identifier)
    card = edit_description(identifier, desc, _cache_dir())
    console.print(f"[green]Description updated: {card.title} [{card.uid6}][/green]")


@card_app.command("move")
@handle_resolve_errors
def move(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    list_target: str = typer.Argument(help="Target list (ID or name)"),
) -> None:
    """Move card to a different list in working copy."""
    from trache.cache.index import resolve_list_name
    from trache.cache.working import move_card

    _warn_if_archived(identifier)
    cache_dir = _cache_dir()
    card = move_card(identifier, list_target, cache_dir)
    list_display = resolve_list_name(card.list_id, cache_dir / "indexes")
    console.print(f"[green]Moved {card.title} [{card.uid6}] to list {list_display}[/green]")


@card_app.command("create")
@handle_resolve_errors
def create(
    list_target: str = typer.Argument(help="Target list (ID or name)"),
    title: str = typer.Argument(help="Card title"),
    desc: str = typer.Option("", "--desc", "-d", help="Card description"),
) -> None:
    """Create a new card in working copy."""
    from trache.cache.working import create_card
    from trache.config import TracheConfig

    config = TracheConfig.load()
    card = create_card(list_target, title, _cache_dir(), config.board_id, desc)
    console.print(f"[green]Created: {card.title} [{card.uid6}] (local only — push to sync)[/green]")


@card_app.command("archive")
@handle_resolve_errors
def archive(
    identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Archive a card in working copy."""
    from trache.cache.working import archive_card

    card = archive_card(identifier, _cache_dir())
    console.print(
        f"[yellow]Archived: {card.title} [{card.uid6}] (local only — push to sync)[/yellow]"
    )


@card_app.command("add-label")
@handle_resolve_errors
def add_label_cmd(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    label: str = typer.Argument(help="Label name to add"),
) -> None:
    """Add a label to a card in working copy."""
    from trache.cache.working import add_label

    _warn_if_archived(identifier)
    card, added = add_label(identifier, label, _cache_dir())
    if added:
        console.print(f"[green]Label '{label}' added to {card.title} [{card.uid6}][/green]")
    else:
        console.print(f"Label '{label}' already present on {card.title} [{card.uid6}]")


@card_app.command("remove-label")
@handle_resolve_errors
def remove_label_cmd(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    label: str = typer.Argument(help="Label name to remove"),
) -> None:
    """Remove a label from a card in working copy."""
    from trache.cache.working import remove_label

    _warn_if_archived(identifier)
    try:
        card = remove_label(identifier, label, _cache_dir())
        console.print(
            f"[green]Label '{label}' removed from {card.title} [{card.uid6}][/green]"
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
