"""Checklist subcommands: show, check, uncheck, add-item, remove-item."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console

from trache.cli._errors import guard_archived, handle_resolve_errors

checklist_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


def _load_checklists_for_card(card_identifier: str) -> tuple[str, list[dict]]:
    """Load all checklists for a card from working cache. Returns (card_id, checklists)."""
    from trache.cache.index import resolve_card_id

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")
    cl_path = cache_dir / "working" / "checklists" / f"{card_id}.json"

    if cl_path.exists():
        return card_id, json.loads(cl_path.read_text())
    return card_id, []


def _save_checklists_for_card(card_id: str, checklists: list[dict]) -> None:
    """Write checklists back to the working directory."""
    cache_dir = _cache_dir()
    cl_dir = cache_dir / "working" / "checklists"
    cl_dir.mkdir(parents=True, exist_ok=True)
    cl_path = cl_dir / f"{card_id}.json"
    cl_path.write_text(json.dumps(checklists, indent=2, default=str) + "\n")


def _update_card_content_modified_at(card_id: str) -> None:
    """Update the card's content_modified_at in the working copy."""
    from trache.cache.store import read_card_file, write_card_file

    cache_dir = _cache_dir()
    card_path = cache_dir / "working" / "cards" / f"{card_id}.md"
    if card_path.exists():
        card = read_card_file(card_path)
        card.content_modified_at = datetime.now(timezone.utc)
        card.dirty = True
        write_card_file(card, cache_dir / "working" / "cards")


@checklist_app.command("show")
@handle_resolve_errors
def show(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Show checklists for a card."""
    _card_id, checklists = _load_checklists_for_card(card_identifier)

    if not checklists:
        console.print("[dim]No checklists[/dim]")
        return

    for cl in checklists:
        console.print(f"\n[bold]{cl['name']}[/bold]")
        for item in cl.get("items", []):
            marker = "[green]x[/green]" if item["state"] == "complete" else "[ ]"
            console.print(f"  {marker} {item['name']}  [dim]({item['id']})[/dim]")


@checklist_app.command("check")
@handle_resolve_errors
def check(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Mark a checklist item as complete (local-first, push to sync)."""
    guard_archived(card_identifier, _cache_dir(), force=force)
    card_id, checklists = _load_checklists_for_card(card_identifier)

    found = False
    already = False
    for cl in checklists:
        for item in cl.get("items", []):
            if item["id"] == item_id:
                already = item["state"] == "complete"
                item["state"] = "complete"
                found = True
                break
        if found:
            break

    if not found:
        console.print(f"[red]Item {item_id} not found[/red]")
        raise typer.Exit(1)

    if already:
        console.print("[dim]Item already complete — no change[/dim]")
        return

    _save_checklists_for_card(card_id, checklists)
    _update_card_content_modified_at(card_id)
    console.print("[green]Item marked complete (local — push to sync)[/green]")


@checklist_app.command("uncheck")
@handle_resolve_errors
def uncheck(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Mark a checklist item as incomplete (local-first, push to sync)."""
    guard_archived(card_identifier, _cache_dir(), force=force)
    card_id, checklists = _load_checklists_for_card(card_identifier)

    found = False
    already = False
    for cl in checklists:
        for item in cl.get("items", []):
            if item["id"] == item_id:
                already = item["state"] == "incomplete"
                item["state"] = "incomplete"
                found = True
                break
        if found:
            break

    if not found:
        console.print(f"[red]Item {item_id} not found[/red]")
        raise typer.Exit(1)

    if already:
        console.print("[dim]Item already incomplete — no change[/dim]")
        return

    _save_checklists_for_card(card_id, checklists)
    _update_card_content_modified_at(card_id)
    console.print("[yellow]Item marked incomplete (local — push to sync)[/yellow]")


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
    guard_archived(card_identifier, _cache_dir(), force=force)
    card_id, checklists = _load_checklists_for_card(card_identifier)

    target_cl = None
    for cl in checklists:
        if cl["name"] == checklist_name:
            target_cl = cl
            break

    if target_cl is None:
        console.print(f"[red]Checklist '{checklist_name}' not found for this card[/red]")
        raise typer.Exit(1)

    # Generate temp ID for the new item
    temp_id = f"temp_{uuid4().hex[:14]}t~"
    max_pos = max((item.get("pos", 0) for item in target_cl.get("items", [])), default=0)
    new_item = {
        "id": temp_id,
        "name": text,
        "state": "incomplete",
        "pos": max_pos + 1024,
    }
    target_cl.setdefault("items", []).append(new_item)

    _save_checklists_for_card(card_id, checklists)
    _update_card_content_modified_at(card_id)
    console.print(f"[green]Added: {text} ({temp_id}) — push to sync[/green]")


@checklist_app.command("remove-item")
@handle_resolve_errors
def remove_item(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
    force: bool = typer.Option(False, "--force", help="Allow editing archived cards"),
) -> None:
    """Remove an item from a checklist (local-first, push to sync)."""
    guard_archived(card_identifier, _cache_dir(), force=force)
    card_id, checklists = _load_checklists_for_card(card_identifier)

    found = False
    for cl in checklists:
        for i, item in enumerate(cl.get("items", [])):
            if item["id"] == item_id:
                cl["items"].pop(i)
                found = True
                break
        if found:
            break

    if not found:
        console.print(f"[red]Item {item_id} not found[/red]")
        raise typer.Exit(1)

    _save_checklists_for_card(card_id, checklists)
    _update_card_content_modified_at(card_id)
    console.print("[yellow]Item removed (local — push to sync)[/yellow]")
