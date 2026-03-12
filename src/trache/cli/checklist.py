"""Checklist subcommands: show, check, uncheck, add-item."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

checklist_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


def _load_checklists_for_card(card_identifier: str) -> list[dict]:
    """Load all checklists for a card from local cache."""
    from trache.cache.index import resolve_card_id

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")
    checklist_dir = cache_dir / "checklists"

    checklists = []
    if checklist_dir.exists():
        for path in checklist_dir.glob("*.json"):
            data = json.loads(path.read_text())
            if data.get("card_id") == card_id:
                checklists.append(data)

    return checklists


@checklist_app.command("show")
def show(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
) -> None:
    """Show checklists for a card."""
    checklists = _load_checklists_for_card(card_identifier)

    if not checklists:
        console.print("[dim]No checklists[/dim]")
        return

    for cl in checklists:
        console.print(f"\n[bold]{cl['name']}[/bold]")
        for item in cl.get("items", []):
            marker = "[green]x[/green]" if item["state"] == "complete" else "[ ]"
            console.print(f"  {marker} {item['name']}  [dim]({item['id']})[/dim]")


@checklist_app.command("check")
def check(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
) -> None:
    """Mark a checklist item as complete (pushes immediately)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        client.update_checklist_item(card_id, item_id, "complete")
    console.print("[green]Item marked complete[/green]")


@checklist_app.command("uncheck")
def uncheck(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    item_id: str = typer.Argument(help="Checklist item ID"),
) -> None:
    """Mark a checklist item as incomplete (pushes immediately)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        client.update_checklist_item(card_id, item_id, "incomplete")
    console.print("[yellow]Item marked incomplete[/yellow]")


@checklist_app.command("add-item")
def add_item(
    checklist_id: str = typer.Argument(help="Checklist ID"),
    text: str = typer.Argument(help="Item text"),
) -> None:
    """Add an item to a checklist (pushes immediately)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.config import TracheConfig

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        item = client.add_checklist_item(checklist_id, text)
    console.print(f"[green]Added: {item.name} ({item.id})[/green]")
