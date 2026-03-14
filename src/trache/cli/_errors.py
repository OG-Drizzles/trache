"""Shared error handling for CLI commands."""

from __future__ import annotations

import functools

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
