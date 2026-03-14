"""Comment subcommands: add, edit, delete, list."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from trache.cli._errors import handle_resolve_errors

comment_app = typer.Typer(no_args_is_help=True)
console = Console()


def _cache_dir() -> Path:
    return Path(".trache")


@comment_app.command("add")
@handle_resolve_errors
def add(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    text: str = typer.Argument(help="Comment text"),
) -> None:
    """Add a comment to a card (pushes immediately)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comment = client.add_comment(card_id, text)
    console.print(f"[green]Comment added ({comment.id}) (API — posted immediately)[/green]")


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
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comment = client.update_comment(card_id, comment_id, text)
    console.print(f"[green]Comment updated ({comment.id}) (API — updated immediately)[/green]")


@comment_app.command("delete")
@handle_resolve_errors
def delete(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    comment_id: str = typer.Argument(help="Comment ID"),
    yes: bool = typer.Option(False, "--yes", help="Confirm deletion"),
) -> None:
    """Delete a comment on a card (deletes immediately via API)."""
    if not yes:
        console.print(
            "[red]Deletion is permanent. Pass --yes to confirm.[/red]"
        )
        raise typer.Exit(1)

    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        client.delete_comment(card_id, comment_id)
    console.print(f"[green]Comment deleted ({comment_id}) (API — deleted immediately)[/green]")


@comment_app.command("list")
@handle_resolve_errors
def list_comments(
    card_identifier: str = typer.Argument(help="Card ID or UID6"),
    compact: bool = typer.Option(False, "--compact", help="One-line-per-comment output"),
) -> None:
    """List comments on a card (fetches from API)."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.cache.index import resolve_card_id
    from trache.config import TracheConfig

    cache_dir = _cache_dir()
    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")

    config = TracheConfig.load()
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    with TrelloClient(auth) as client:
        comments = client.get_card_comments(card_id)

    if not comments:
        console.print("[dim]No comments (fetched from API)[/dim]")
        return

    if compact:
        console.print(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
        for c in comments:
            date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
            author = c.author or "unknown"
            char_count = len(c.text)
            preview = c.text.replace("\n", " ")[:80]
            console.print(
                f"  {date_str}  {author}  [{c.id}]  ({char_count} chars)  {preview}"
            )
        return

    console.print(f"[dim]{len(comments)} comment(s) (fetched from API)[/dim]")
    for c in comments:
        date_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "?"
        console.print(f"[bold]{c.author}[/bold] ({date_str}) [dim][{c.id}][/dim]:")
        console.print(f"  {c.text}")
        console.print()
