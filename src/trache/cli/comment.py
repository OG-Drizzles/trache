"""Comment subcommands: add, edit, delete, list."""

from __future__ import annotations

from pathlib import Path

import typer

from trache.cli._errors import handle_resolve_errors
from trache.cli._output import get_output

comment_app = typer.Typer(no_args_is_help=True)


def _cache_dir() -> Path:
    from trache.cli._context import resolve_cache_dir
    return resolve_cache_dir()


@comment_app.command("add")
@handle_resolve_errors
def add(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    text: str = typer.Argument(help="Comment text"),
) -> None:
    """Add a comment to a card (pushes immediately)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.db import resolve_card_id
    from trache.config import TracheConfig

    out = get_output()
    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)

    config = TracheConfig.load(cache_dir)
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comment = client.add_comment(card_id, text)
    if out.is_human:
        out.human(f"[green]Comment added ({comment.id}) (API — posted immediately)[/green]")
    else:
        out.json({"ok": True, "comment_id": comment.id})


@comment_app.command("edit")
@handle_resolve_errors
def edit(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    comment_id: str = typer.Argument(help="Comment ID"),
    text: str = typer.Argument(help="New comment text"),
) -> None:
    """Edit a comment on a card (updates immediately via API)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.db import resolve_card_id
    from trache.config import TracheConfig

    out = get_output()
    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)

    config = TracheConfig.load(cache_dir)
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comment = client.update_comment(card_id, comment_id, text)
    if out.is_human:
        out.human(f"[green]Comment updated ({comment.id}) (API — updated immediately)[/green]")
    else:
        out.json({"ok": True, "comment_id": comment.id})


@comment_app.command("delete")
@handle_resolve_errors
def delete(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    comment_id: str = typer.Argument(help="Comment ID"),
    yes: bool = typer.Option(False, "--yes", help="Confirm deletion"),
) -> None:
    """Delete a comment on a card (deletes immediately via API)."""
    out = get_output()

    if not yes:
        out.error("Deletion is permanent. Pass --yes to confirm.")
        raise typer.Exit(1)

    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.db import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)

    config = TracheConfig.load(cache_dir)
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        client.delete_comment(card_id, comment_id)
    if out.is_human:
        out.human(f"[green]Comment deleted ({comment_id}) (API — deleted immediately)[/green]")
    else:
        out.json({"ok": True, "comment_id": comment_id})


@comment_app.command("list")
@handle_resolve_errors
def list_comments(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    compact: bool = typer.Option(False, "--compact", help="One-line-per-comment output"),
) -> None:
    """List comments on a card (fetches from API)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.db import resolve_card_id
    from trache.config import TracheConfig

    out = get_output()
    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir)

    config = TracheConfig.load(cache_dir)
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comments = client.get_card_comments(card_id)

    if not comments:
        if out.is_human:
            out.human("[dim]No comments (fetched from API)[/dim]")
        else:
            out.json([])
        return

    if not out.is_human:
        out.json([
            {
                "id": c.id,
                "author": c.author,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "text": c.text,
            }
            for c in comments
        ])
        return

    if compact:
        out.human(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
        for c in comments:
            date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
            author = c.author or "unknown"
            char_count = len(c.text)
            preview = c.text.replace("\n", " ")[:80]
            out.human(
                f"  {date_str}  {author}  [{c.id}]  ({char_count} chars)  {preview}"
            )
        return

    out.human(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
    for c in comments:
        date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
        out.human(f"[bold]{c.author}[/bold] ({date_str}) [dim][{c.id}][/dim]:")
        out.human(f"  {c.text}")
        out.human("")
