"""Label subcommands: list, create, delete."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

label_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


def _labels_path() -> Path:
    return _cache_dir() / "working" / "labels.json"


def _load_labels() -> list[dict]:
    path = _labels_path()
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _save_labels(labels: list[dict]) -> None:
    path = _labels_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(labels, indent=2) + "\n")


@label_app.command("list")
def list_labels() -> None:
    """List board labels (reads local cache, no API call)."""
    labels_path = _labels_path()

    if not labels_path.exists():
        console.print("[dim]No labels found. Run `trache pull` first.[/dim]")
        raise typer.Exit(1)

    labels = json.loads(labels_path.read_text())

    if not labels:
        console.print("[dim]No labels on this board.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Color")

    for lbl in labels:
        name = lbl.get("name", "")
        color = lbl.get("color", "")
        if name:
            table.add_row(name, color)
        else:
            table.add_row(f"[dim](unnamed)[/dim]", color)

    console.print(table)


@label_app.command("create")
def create(
    name: str = typer.Argument(help="Label name"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Label color"),
) -> None:
    """Create a new board label (local-first, push to sync)."""
    labels = _load_labels()

    # Check for duplicate name
    for lbl in labels:
        if lbl.get("name") == name:
            console.print(f"[red]Label '{name}' already exists[/red]")
            raise typer.Exit(1)

    temp_id = f"temp_{uuid4().hex[:14]}t~"
    entry: dict = {"id": temp_id, "name": name, "color": color}
    labels.append(entry)
    _save_labels(labels)

    color_info = color or "no color"
    console.print(
        f"[green]Label created: {name} ({color_info}) ({temp_id}) "
        f"(local — push to sync)[/green]"
    )


@label_app.command("delete")
def delete(
    name: str = typer.Argument(help="Label name"),
) -> None:
    """Delete a board label (local-first, push to sync)."""
    labels = _load_labels()

    target_idx = None
    for i, lbl in enumerate(labels):
        if lbl.get("name") == name:
            target_idx = i
            break

    if target_idx is None:
        console.print(f"[red]Label '{name}' not found[/red]")
        raise typer.Exit(1)

    # Warn if any cards use this label
    cache_dir = _cache_dir()
    working_cards_dir = cache_dir / "working" / "cards"
    if working_cards_dir.exists():
        from trache.cache.store import list_card_files, read_card_file

        using_cards = []
        for card_path in list_card_files(working_cards_dir):
            card = read_card_file(card_path)
            if name in card.labels:
                using_cards.append(card.title)
        if using_cards:
            console.print(
                f"[yellow]Warning: {len(using_cards)} card(s) use this label: "
                f"{', '.join(using_cards[:5])}[/yellow]"
            )

    labels.pop(target_idx)
    _save_labels(labels)
    console.print(f"[yellow]Label deleted: {name} (local — push to sync)[/yellow]")
