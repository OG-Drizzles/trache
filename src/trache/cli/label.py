"""Label subcommands: list board labels."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

label_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


@label_app.command("list")
def list_labels() -> None:
    """List board labels (reads local cache, no API call)."""
    labels_path = _cache_dir() / "working" / "labels.json"

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
