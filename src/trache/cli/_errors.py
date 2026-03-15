"""Shared error handling for CLI commands."""

from __future__ import annotations

import functools
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def handle_resolve_errors(func):
    """Catch KeyError from identifier resolution and print a friendly message."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyError as e:
            msg = e.args[0] if e.args else "Requested item not found"
            console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    return wrapper


def guard_archived(identifier: str, cache_dir: Path, *, force: bool = False) -> "Card | None":
    """Block edits to archived cards unless --force is set.

    Returns the loaded Card on success (so callers can reuse it), or None
    if the card was not found (letting the actual command handle the error).

    Raises typer.Exit(1) if the card is archived and force is False.
    Prints a warning if force is True.
    """
    from trache.cache.models import Card
    from trache.cache.working import read_working_card

    try:
        card = read_working_card(identifier, cache_dir)
        if card.closed:
            if force:
                console.print(
                    f"[yellow]Warning: card [{card.uid6}] is archived — "
                    f"proceeding due to --force.[/yellow]"
                )
            else:
                console.print(
                    f"[red]Card [{card.uid6}] is archived. "
                    f"Use --force to edit archived cards.[/red]"
                )
                raise typer.Exit(1)
        return card
    except (KeyError, FileNotFoundError):
        return None  # Card not found — let the actual command handle the error
