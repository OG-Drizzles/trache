"""Checklist subcommands: show, check, uncheck, add-item, remove-item, create."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer

from trache.cli._errors import guard_archived, handle_resolve_errors
from trache.cli._output import get_output

checklist_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


@checklist_app.command("create")
@handle_resolve_errors
def create(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    name: str = typer.Argument(help="Checklist name"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Create a new checklist on a card (local-first, push to sync)."""
    from trache.cache.db import (
        read_card,
        read_checklists_raw,
        resolve_card_id,
        write_card,
        write_checklists_raw,
    )

    out = get_output()
    cache_dir = _cache_dir()
    guard_archived(card_identifier, cache_dir, force=force)
    card_id = resolve_card_id(card_identifier, cache_dir)
    checklists = read_checklists_raw(card_id, "working", cache_dir)

    # Check for duplicate name
    for cl in checklists:
        if cl["name"] == name:
            out.error(f"Checklist '{name}' already exists on this card")
            raise typer.Exit(1)

    temp_id = f"temp_{uuid4().hex[:14]}t~"
    checklists.append({"id": temp_id, "name": name, "items": []})

    write_checklists_raw(card_id, checklists, "working", cache_dir)
    # Dirty the card
    try:
        card = read_card(card_id, "working", cache_dir)
        card.content_modified_at = datetime.now(timezone.utc)
        card.dirty = True
        write_card(card, "working", cache_dir)
    except FileNotFoundError:
        pass

    if out.is_human:
        out.human(f"[green]Checklist created: {name} ({temp_id}) — push to sync[/green]")
    else:
        out.json({"ok": True, "name": name, "id": temp_id})


@checklist_app.command("show")
@handle_resolve_errors
def show(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Show checklists for a card."""
    from trache.cache.db import read_checklists_raw, resolve_card_id

    out = get_output()
    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)
    checklists = read_checklists_raw(card_id, "working", cache_dir)

    if not checklists:
        if out.is_human:
            out.human("[dim]No checklists[/dim]")
        else:
            out.json([])
        return

    if not out.is_human:
        out.json(checklists)
        return

    for cl in checklists:
        out.human(f"\n[bold]{cl['name']}[/bold]")
        for item in cl.get("items", []):
            marker = "[green]x[/green]" if item["state"] == "complete" else "[ ]"
            out.human(f"  {marker} {item['name']}  [dim]({item['id']})[/dim]")


@checklist_app.command("check")
@handle_resolve_errors
def check(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Mark a checklist item as complete (local-first, push to sync)."""
    from trache.cache.working import check_checklist_item

    out = get_output()
    cache_dir = _cache_dir()
    guard_archived(card_identifier, cache_dir, force=force)

    result = check_checklist_item(card_identifier, item_id, cache_dir)

    if not result["changed"]:
        if out.is_human:
            out.human("[dim]Item already complete — no change[/dim]")
        else:
            out.json({"ok": True, "item_id": item_id, "changed": False})
        return

    if out.is_human:
        out.human("[green]Item marked complete (local — push to sync)[/green]")
    else:
        out.json({"ok": True, "item_id": item_id, "changed": True})


@checklist_app.command("uncheck")
@handle_resolve_errors
def uncheck(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Mark a checklist item as incomplete (local-first, push to sync)."""
    from trache.cache.working import uncheck_checklist_item

    out = get_output()
    cache_dir = _cache_dir()
    guard_archived(card_identifier, cache_dir, force=force)

    result = uncheck_checklist_item(card_identifier, item_id, cache_dir)

    if not result["changed"]:
        if out.is_human:
            out.human("[dim]Item already incomplete — no change[/dim]")
        else:
            out.json({"ok": True, "item_id": item_id, "changed": False})
        return

    if out.is_human:
        out.human("[yellow]Item marked incomplete (local — push to sync)[/yellow]")
    else:
        out.json({"ok": True, "item_id": item_id, "changed": True})


@checklist_app.command("add-item")
@handle_resolve_errors
def add_item(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    checklist_name: str = typer.Argument(
        help="Checklist name (exact match — use 'checklist show' to see names)"
    ),
    text: str = typer.Argument(help="Item text"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Add an item to a checklist by name (local-first, push to sync)."""
    from trache.cache.working import add_checklist_item

    out = get_output()
    cache_dir = _cache_dir()
    guard_archived(card_identifier, cache_dir, force=force)

    result = add_checklist_item(card_identifier, checklist_name, text, cache_dir)

    if out.is_human:
        out.human(f"[green]Added: {text} ({result['item_id']}) — push to sync[/green]")
    else:
        out.json({"ok": True, "item_id": result["item_id"], "text": text})


@checklist_app.command("remove-item")
@handle_resolve_errors
def remove_item(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Remove an item from a checklist (local-first, push to sync)."""
    from trache.cache.working import remove_checklist_item

    out = get_output()
    cache_dir = _cache_dir()
    guard_archived(card_identifier, cache_dir, force=force)

    remove_checklist_item(card_identifier, item_id, cache_dir)

    if out.is_human:
        out.human("[yellow]Item removed (local — push to sync)[/yellow]")
    else:
        out.json({"ok": True, "item_id": item_id})
