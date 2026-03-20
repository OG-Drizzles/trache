"""Comment subcommands: add, edit, delete, list."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.markup import escape

from trache.cli._errors import handle_resolve_errors
from trache.cli._output import get_output

comment_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


def _confirm_api_direct(out, action_description: str) -> None:
    """Fail-closed confirmation guard for API-direct comment commands.

    - Machine mode: always exit 1 (pass --yes to bypass).
    - Human mode + non-TTY stdin: exit 1 (cannot prompt).
    - Human mode + TTY: typer.confirm() with default=No; No/Abort/EOF/Ctrl-C all exit 1.
    """
    if not out.is_human:
        out.error(
            "Comment commands are API-direct (not staged). "
            "Pass --yes to confirm."
        )
        raise typer.Exit(1)

    if not sys.stdin.isatty():
        out.error(
            "Comment commands are API-direct (not staged). "
            "Pass --yes to confirm, or run in an interactive terminal."
        )
        raise typer.Exit(1)

    try:
        confirmed = typer.confirm(
            f"This will {action_description} immediately on Trello "
            "(API-direct, not staged). Proceed?",
            default=False,
        )
    except (typer.Abort, EOFError, KeyboardInterrupt):
        raise typer.Exit(1)
    if not confirmed:
        raise typer.Exit(1)


@comment_app.command("add")
@handle_resolve_errors
def add(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    text: str = typer.Argument(help="Comment text"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm API-direct action"),
) -> None:
    """Add a comment to a card (pushes immediately)."""
    out = get_output()

    if not yes:
        _confirm_api_direct(out, "post this comment")

    from trache.cache.db import resolve_card_id
    from trache.cli._context import get_client_and_config

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)
    client, _config = get_client_and_config(cache_dir)
    with client:
        comment = client.add_comment(card_id, text)
    if out.is_human:
        out.human(f"[green]Comment added ({comment.id}) (API — posted immediately)[/green]")
    else:
        out.json({"ok": True, "api_direct": True, "comment_id": comment.id})


@comment_app.command("edit")
@handle_resolve_errors
def edit(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    comment_id: str = typer.Argument(help="Comment ID"),
    text: str = typer.Argument(help="New comment text"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm API-direct action"),
) -> None:
    """Edit a comment on a card (updates immediately via API)."""
    out = get_output()

    if not yes:
        _confirm_api_direct(out, "update this comment")

    from trache.cache.db import resolve_card_id
    from trache.cli._context import get_client_and_config

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)
    client, _config = get_client_and_config(cache_dir)
    with client:
        comment = client.update_comment(card_id, comment_id, text)
    if out.is_human:
        out.human(f"[green]Comment updated ({comment.id}) (API — updated immediately)[/green]")
    else:
        out.json({"ok": True, "api_direct": True, "comment_id": comment.id})


@comment_app.command("delete")
@handle_resolve_errors
def delete(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    comment_id: str = typer.Argument(help="Comment ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion"),
) -> None:
    """Delete a comment on a card (deletes immediately via API)."""
    out = get_output()

    if not yes:
        _confirm_api_direct(out, "delete this comment permanently")

    from trache.cache.db import resolve_card_id
    from trache.cli._context import get_client_and_config

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)
    client, _config = get_client_and_config(cache_dir)
    with client:
        client.delete_comment(card_id, comment_id)
    if out.is_human:
        out.human(f"[green]Comment deleted ({comment_id}) (API — deleted immediately)[/green]")
    else:
        out.json({"ok": True, "api_direct": True, "comment_id": comment_id})


@comment_app.command("list")
@handle_resolve_errors
def list_comments(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    compact: bool = typer.Option(False, "--compact", help="One-line-per-comment output"),
) -> None:
    """List comments on a card (fetches from API)."""
    from trache.cache.db import resolve_card_id
    from trache.cli._context import get_client_and_config

    out = get_output()
    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)
    client, _config = get_client_and_config(cache_dir)
    with client:
        comments = client.get_card_comments(card_id)

    if not comments:
        if out.is_human:
            out.human("[dim]No comments (fetched from API)[/dim]")
        else:
            out.json({"api_direct": True, "comments": []})
        return

    if not out.is_human:
        out.json({"api_direct": True, "comments": [
            {
                "id": c.id,
                "author": c.author,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "text": c.text,
            }
            for c in comments
        ]})
        return

    if compact:
        out.human(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
        for c in comments:
            date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
            author = c.author or "unknown"
            char_count = len(c.text)
            preview = c.text.replace("\n", " ")[:80]
            out.human(
                f"  {date_str}  {escape(author)}  [{c.id}]  ({char_count} chars)  {escape(preview)}"
            )
        return

    out.human(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
    for c in comments:
        date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
        out.human(f"[bold]{escape(c.author)}[/bold] ({date_str}) [dim][{c.id}][/dim]:")
        out.human(f"  {escape(c.text)}")
        out.human("")
