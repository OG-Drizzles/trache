"""Label subcommands: list, create, delete."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer
from rich.table import Table

from trache.cache.db import list_cards, read_labels_raw, write_labels_raw
from trache.cli._output import get_output

label_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


@label_app.command("list")
def list_labels() -> None:
    """List board labels (reads local cache, no API call)."""
    out = get_output()
    cache_dir = _cache_dir()
    labels = read_labels_raw("working", cache_dir)

    if not labels:
        if out.is_human:
            out.human("[dim]No labels found. Run `trache pull` first.[/dim]")
        else:
            out.tsv([], header=["name", "color"])
        return

    if out.is_human:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name")
        table.add_column("Color")

        for lbl in labels:
            name = lbl.get("name", "")
            color = lbl.get("color", "")
            if name:
                table.add_row(name, color)
            else:
                table.add_row("[dim](unnamed)[/dim]", color)

        out.human_table(table)
    else:
        rows = []
        for lbl in labels:
            name = lbl.get("name", "")
            color = lbl.get("color", "")
            if name:
                rows.append([name, color])
        out.tsv(rows, header=["name", "color"])


@label_app.command("create")
def create(
    name: str = typer.Argument(help="Label name"),
    color: Optional[str] = typer.Option(None, "--color", "-c", help="Label color"),
) -> None:
    """Create a new board label (local-first, push to sync)."""
    out = get_output()
    cache_dir = _cache_dir()
    labels = read_labels_raw("working", cache_dir)

    # Check for duplicate name
    for lbl in labels:
        if lbl.get("name") == name:
            out.error(f"Label '{name}' already exists")
            raise typer.Exit(1)

    temp_id = f"temp_{uuid4().hex[:14]}t~"
    entry: dict = {"id": temp_id, "name": name, "color": color}
    labels.append(entry)
    write_labels_raw(labels, "working", cache_dir)

    if out.is_human:
        color_info = color or "no color"
        out.human(
            f"[green]Label created: {name} ({color_info}) ({temp_id}) "
            f"(local — push to sync)[/green]"
        )
    else:
        out.json({"ok": True, "name": name, "color": color, "id": temp_id})


@label_app.command("delete")
def delete(
    name: str = typer.Argument(help="Label name"),
) -> None:
    """Delete a board label (local-first, push to sync)."""
    out = get_output()
    cache_dir = _cache_dir()
    labels = read_labels_raw("working", cache_dir)

    target_idx = None
    for i, lbl in enumerate(labels):
        if lbl.get("name") == name:
            target_idx = i
            break

    if target_idx is None:
        out.error(f"Label '{name}' not found")
        raise typer.Exit(1)

    # Warn if any cards use this label
    working_cards = list_cards("working", cache_dir)
    using_cards = [c.title for c in working_cards if name in c.labels]
    if using_cards:
        out.human(
            f"[yellow]Warning: {len(using_cards)} card(s) use this label: "
            f"{', '.join(using_cards[:5])}[/yellow]"
        )

    labels.pop(target_idx)
    write_labels_raw(labels, "working", cache_dir)
    if out.is_human:
        out.human(f"[yellow]Label deleted: {name} (local — push to sync)[/yellow]")
    else:
        out.json({"ok": True, "name": name})
