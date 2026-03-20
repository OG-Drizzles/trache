"""Card subcommands: list, show, edit-title, edit-desc, move, create, archive, labels."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.markup import escape
from rich.table import Table

from trache.cli._errors import guard_archived, handle_resolve_errors
from trache.cli._output import get_output

card_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


@card_app.command("list")
@handle_resolve_errors
def list_cards(
    list_name: Optional[str] = typer.Option(
        None, "--list", "-l", help="Filter by list (ID or name)"
    ),
) -> None:
    """List cards from local index (no API call)."""
    from trache.cache.db import load_cards_index, read_lists, resolve_list_id

    cache_dir = _cache_dir()
    cards_index = load_cards_index(cache_dir)
    lists_index = read_lists(cache_dir)
    out = get_output()

    # Build list name lookup
    list_names = {lid: info["name"] for lid, info in lists_index.items()}

    # Filter by list if specified
    filter_list_id = None
    if list_name:
        filter_list_id = resolve_list_id(list_name, cache_dir)

    if out.is_human:
        table = Table(show_header=True, header_style="bold")
        table.add_column("UID6", style="cyan", width=8)
        table.add_column("List", width=20)
        table.add_column("Title")

        for card_id, info in cards_index.items():
            if filter_list_id and info["list_id"] != filter_list_id:
                continue
            list_display = list_names.get(info["list_id"], info["list_id"][:8])
            table.add_row(info["uid6"], list_display, info["title"])

        out.human_table(table)
    else:
        rows = []
        for card_id, info in cards_index.items():
            if filter_list_id and info["list_id"] != filter_list_id:
                continue
            list_display = list_names.get(info["list_id"], info["list_id"][:8])
            rows.append([info["uid6"], list_display, info["title"]])
        out.tsv(rows, header=["uid6", "list", "title"])


@card_app.command("show")
@handle_resolve_errors
def show_card(
    identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Show a single card (no API call)."""
    from trache.cache.db import read_checklists, resolve_list_name
    from trache.cache.working import read_working_card

    cache_dir = _cache_dir()
    card = read_working_card(identifier, cache_dir)
    out = get_output()

    if not out.is_human:
        from trache.cache.db import read_checklists_raw, resolve_list_name

        list_name = resolve_list_name(card.list_id, cache_dir)
        checklists_data = read_checklists_raw(card.id, "working", cache_dir)
        data = {
            "id": card.id,
            "uid6": card.uid6,
            "title": card.title,
            "description": card.description,
            "list_id": card.list_id,
            "list_name": list_name,
            "labels": card.labels,
            "due": card.due.isoformat() if card.due else None,
            "closed": card.closed,
            "dirty": card.dirty,
            "checklists": checklists_data,
        }
        out.json(data)
        return

    # Load checklists from database
    card.checklists = read_checklists(card.id, "working", cache_dir)

    # Title (truncate pathological lengths)
    if len(card.title) > 120:
        title_display = card.title[:120] + f"… (len={len(card.title)})"
    else:
        title_display = card.title
    out.human(f"[bold]{escape(title_display)}[/bold]  [{card.uid6}]")

    # List name
    list_display = resolve_list_name(card.list_id, cache_dir)
    out.human(f"List: {escape(list_display)}")

    # Status line
    status_parts = []
    if card.closed:
        status_parts.append("[red]ARCHIVED[/red]")
    if card.dirty:
        status_parts.append("[yellow]MODIFIED[/yellow]")
    if not status_parts:
        status_parts.append("[green]CLEAN[/green]")
    out.human(f"Status: {' | '.join(status_parts)}")

    if card.labels:
        out.human(f"Labels: {escape(', '.join(card.labels))}")
    if card.due:
        out.human(f"Due: {card.due}")
    out.human("")
    if card.description:
        out.human(escape(card.description))
    else:
        out.human("[dim]No description[/dim]")
    if card.checklists:
        out.human("")
        for cl in card.checklists:
            out.human(f"[bold]{escape(cl.name)}[/bold]: {cl.complete}/{cl.total} complete")
            for item in cl.items:
                check = "\\[x]" if item.state == "complete" else "\\[ ]"
                out.human(f"  {check} {escape(item.name)} [dim]({item.id})[/dim]")


@card_app.command("edit-title")
@handle_resolve_errors
def edit_title(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    title: str = typer.Argument(help="New title"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Edit card title in working copy."""
    from trache.cache.working import edit_title as _edit_title

    cache_dir = _cache_dir()
    out = get_output()
    guarded = guard_archived(identifier, cache_dir, force=force)
    card = _edit_title(guarded.id if guarded else identifier, title, cache_dir)
    if out.is_human:
        out.human(f"[green]Title updated: {escape(card.title)} [{card.uid6}][/green]")
    else:
        out.json({"ok": True, "uid6": card.uid6, "title": card.title})


@card_app.command("edit-desc")
@handle_resolve_errors
def edit_desc(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    desc: str = typer.Argument(help="New description"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Edit card description in working copy."""
    from trache.cache.working import edit_description

    cache_dir = _cache_dir()
    out = get_output()
    guarded = guard_archived(identifier, cache_dir, force=force)
    card = edit_description(guarded.id if guarded else identifier, desc, cache_dir)
    if out.is_human:
        out.human(f"[green]Description updated: {escape(card.title)} [{card.uid6}][/green]")
    else:
        out.json({
            "ok": True, "uid6": card.uid6, "title": card.title, "description": card.description,
        })


@card_app.command("move")
@handle_resolve_errors
def move(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    list_target: str = typer.Argument(help="Target list (ID or name)"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Move card to a different list in working copy."""
    from trache.cache.db import resolve_list_name
    from trache.cache.working import move_card

    cache_dir = _cache_dir()
    out = get_output()
    guarded = guard_archived(identifier, cache_dir, force=force)
    card = move_card(guarded.id if guarded else identifier, list_target, cache_dir)
    list_display = resolve_list_name(card.list_id, cache_dir)
    if out.is_human:
        out.human(
            f"[green]Moved {escape(card.title)} [{card.uid6}]"
            f" to list {escape(list_display)}[/green]"
        )
    else:
        out.json({
            "ok": True,
            "uid6": card.uid6,
            "title": card.title,
            "list_id": card.list_id,
            "list_name": list_display,
        })


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

    cache_dir = _cache_dir()
    out = get_output()
    config = TracheConfig.load(cache_dir)
    card = create_card(list_target, title, cache_dir, config.board_id, desc)
    if out.is_human:
        out.human(
            f"[green]Created: {escape(card.title)} [{card.uid6}]"
            f" (local only — push to sync)[/green]"
        )
    else:
        out.json({"ok": True, "uid6": card.uid6, "title": card.title, "list_id": card.list_id})


@card_app.command("archive")
@handle_resolve_errors
def archive(
    identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Archive a card in working copy."""
    from trache.cache.working import archive_card

    out = get_output()
    card = archive_card(identifier, _cache_dir())
    if out.is_human:
        out.human(
            f"[yellow]Archived: {escape(card.title)} [{card.uid6}]"
            f" (local only — push to sync)[/yellow]"
        )
    else:
        out.json({"ok": True, "uid6": card.uid6, "title": card.title})


@card_app.command("add-label")
@handle_resolve_errors
def add_label_cmd(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    label: str = typer.Argument(help="Label name to add"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Add a label to a card in working copy."""
    from trache.cache.working import add_label

    cache_dir = _cache_dir()
    out = get_output()
    guarded = guard_archived(identifier, cache_dir, force=force)
    card, added = add_label(guarded.id if guarded else identifier, label, cache_dir)
    if out.is_human:
        if added:
            out.human(
                f"[green]Label '{escape(label)}' added to"
                f" {escape(card.title)} [{card.uid6}][/green]"
            )
        else:
            out.human(
                f"Label '{escape(label)}' already present on"
                f" {escape(card.title)} [{card.uid6}]"
            )
    else:
        out.json({
            "ok": True, "uid6": card.uid6, "title": card.title, "label": label, "added": added,
        })


@card_app.command("remove-label")
@handle_resolve_errors
def remove_label_cmd(
    identifier: str = typer.Argument(help="Card ID or UID6"),
    label: str = typer.Argument(help="Label name to remove"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Remove a label from a card in working copy."""
    from trache.cache.working import remove_label

    cache_dir = _cache_dir()
    out = get_output()
    guarded = guard_archived(identifier, cache_dir, force=force)
    try:
        card = remove_label(guarded.id if guarded else identifier, label, cache_dir)
        if out.is_human:
            out.human(
                f"[green]Label '{escape(label)}' removed from"
                f" {escape(card.title)} [{card.uid6}][/green]"
            )
        else:
            out.json({"ok": True, "uid6": card.uid6, "title": card.title, "label": label})
    except ValueError as e:
        out.error(str(e))
        raise typer.Exit(1)
