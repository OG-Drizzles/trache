"""Shared error handling for CLI commands."""

from __future__ import annotations

import functools
from pathlib import Path

import typer

from trache.cache.models import Card
from trache.cli._output import get_output


def handle_resolve_errors(func):
    """Catch KeyError from identifier resolution and print a friendly message."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyError as e:
            msg = e.args[0] if e.args else "Requested item not found"
            get_output().error(msg)
            raise typer.Exit(1)
        except ValueError as e:
            get_output().error(str(e))
            raise typer.Exit(1)

    return wrapper


def guard_archived(identifier: str, cache_dir: Path, *, force: bool = False) -> Card | None:
    """Block edits to archived cards unless --force is set.

    Returns the loaded Card on success (so callers can reuse it), or None
    if the card was not found (letting the actual command handle the error).

    Raises typer.Exit(1) if the card is archived and force is False.
    Prints a warning if force is True.
    """
    from trache.cache.working import read_working_card

    out = get_output()
    try:
        card = read_working_card(identifier, cache_dir)
        if card.closed:
            if force:
                out.human(
                    f"[yellow]Warning: card [{card.uid6}] is archived — "
                    f"proceeding due to --force.[/yellow]"
                )
            else:
                out.error(
                    f"Card [{card.uid6}] is archived. "
                    f"Use --force to edit archived cards."
                )
                raise typer.Exit(1)
        return card
    except (KeyError, FileNotFoundError):
        return None  # Card not found — let the actual command handle the error
