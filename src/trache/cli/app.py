"""Typer app root: init, pull, push, sync, status, diff."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import os

import httpx
import typer
from rich.console import Console
from rich.markup import escape

from trache import __version__
from trache.cli._context import (
    TRACHE_ROOT,
    get_client_and_config,
    list_board_names,
    resolve_cache_dir,
    set_active_board,
    set_board_override,
    slugify,
)
from trache.cli.board import board_app
from trache.cli.card import card_app
from trache.cli.checklist import checklist_app
from trache.cli.comment import comment_app
from trache.cli.label import label_app
from trache.cli.list_cmd import list_app

app = typer.Typer(
    name="trache",
    help="Local-first Trello cache with Git-style sync, optimised for AI-agent workflows.",
    no_args_is_help=True,
)
app.add_typer(board_app, name="board", help="Board management")
app.add_typer(card_app, name="card", help="Card operations")
app.add_typer(checklist_app, name="checklist", help="Checklist operations")
app.add_typer(comment_app, name="comment", help="Comment operations")
app.add_typer(label_app, name="label", help="Label operations")
app.add_typer(list_app, name="list", help="List operations")

console = Console()


@app.callback()
def main(
    board: Optional[str] = typer.Option(
        None, "--board", "-B", help="Board alias to operate on"
    ),
) -> None:
    """Local-first Trello cache with Git-style sync."""
    set_board_override(board)


def _get_client(cache_dir: Path):
    """Create an authenticated Trello client from config."""
    return get_client_and_config(cache_dir)


@app.command()
def init(
    board_id: str = typer.Option(None, "--board-id", "-b", help="Trello board ID"),
    board_url: str = typer.Option(None, "--board-url", "-u", help="Trello board URL"),
    auth: bool = typer.Option(False, "--auth", help="Print auth/token setup guidance"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Short alias for this board"),
    new: Optional[str] = typer.Option(None, "--new", help="Create a new Trello board with this name"),
) -> None:
    """Initialise Trache cache for a board."""
    from trache.config import TracheConfig, ensure_cache_structure

    # --new and --board-id/--board-url are mutually exclusive
    if new and (board_id or board_url):
        console.print("[red]Cannot use --new with --board-id or --board-url[/red]")
        raise typer.Exit(1)

    config = TracheConfig(board_id=board_id or "pending")

    # Detect auth state from env vars
    api_key_val = os.environ.get(config.api_key_env)
    token_val = os.environ.get(config.token_env)
    auth_configured = bool(api_key_val and token_val)

    # Handle --new: create board on Trello
    if new:
        if not auth_configured:
            console.print("[red]Auth must be configured to create a board. Set TRELLO_API_KEY and TRELLO_TOKEN.[/red]")
            raise typer.Exit(1)

        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth_obj = TrelloAuth.from_env(config.api_key_env, config.token_env)
        with TrelloClient(auth_obj) as client:
            board_obj = client.create_board(new)
            board_id = board_obj.id
            config.board_id = board_id
            config.board_name = board_obj.name
            console.print(f"[green]Created board: {board_obj.name} on Trello[/green]")

    if not board_id and not board_url and not new:
        board_id = typer.prompt("Board ID")

    if board_url and not board_id:
        # Extract board ID from URL: https://trello.com/b/<shortLink>/...
        parts = board_url.rstrip("/").split("/")
        try:
            b_idx = parts.index("b")
            board_id = parts[b_idx + 1]
        except (ValueError, IndexError):
            console.print("[red]Could not extract board ID from URL[/red]")
            raise typer.Exit(1)

    if board_id:
        config.board_id = board_id

    # Show auth guidance if --auth flag or auth not configured
    from trache.cli.agents import print_auth_guidance

    if auth or not auth_configured:
        print_auth_guidance(
            api_key_val or None,
            key_env=config.api_key_env,
            token_env=config.token_env,
        )

    # Token validation and board name fetch (skip if --new already did this)
    if not new:
        if not auth_configured:
            console.print(
                "[yellow]Auth not configured — skipping board name fetch and token validation.[/yellow]"
            )
        else:
            from trache.api.auth import TrelloAuth
            from trache.api.client import TrelloClient

            auth_obj = TrelloAuth.from_env(config.api_key_env, config.token_env)
            with TrelloClient(auth_obj) as client:
                # Validate token
                try:
                    member = client.get_current_member()
                    member_name = member.get("fullName") or member.get("username", "unknown")
                    console.print(f"[green]Token valid — authenticated as {member_name}[/green]")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        console.print("[red]Token validation failed (401 Unauthorized)[/red]")
                    else:
                        raise

                # Fetch board name (best-effort)
                try:
                    board_obj = client.get_board(config.board_id)
                    config.board_name = board_obj.name
                    console.print(f"Board: [bold]{board_obj.name}[/bold]")
                except Exception:
                    console.print(
                        "[yellow]Could not fetch board name[/yellow]"
                    )

    # Determine alias
    alias = name
    if not alias:
        alias = slugify(config.board_name) if config.board_name else slugify(config.board_id[:12])

    # Check for alias collision
    existing = list_board_names()
    if alias in existing:
        console.print(
            f"[red]Board alias '{alias}' already exists. Use --name to choose a different alias.[/red]"
        )
        raise typer.Exit(1)

    # Create multi-board directory structure
    TRACHE_ROOT.mkdir(parents=True, exist_ok=True)
    boards_dir = TRACHE_ROOT / "boards"
    boards_dir.mkdir(exist_ok=True)
    cache_dir = boards_dir / alias

    ensure_cache_structure(cache_dir)
    config.save(cache_dir)

    # Set active if first board or no active board
    active_file = TRACHE_ROOT / "active"
    if not active_file.exists() or not active_file.read_text().strip():
        set_active_board(alias)
    elif len(list_board_names()) == 1:
        set_active_board(alias)

    console.print(f"[green]Initialised board '{alias}' for {config.board_id}[/green]")

    from trache.cli.agents import print_init_agent_guidance

    print_init_agent_guidance(board_name=getattr(config, "board_name", None))


@app.command()
def pull(
    card: Optional[str] = typer.Option(None, "--card", "-c", help="Pull single card (ID or UID6)"),
    list_name: Optional[str] = typer.Option(
        None, "--list", "-l", help="Pull all cards in list (ID or name)"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite dirty working state"),
) -> None:
    """Pull data from Trello into local cache."""
    from trache.sync.pull import pull_card, pull_full_board, pull_list

    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    try:
        with client:
            if card:
                result = pull_card(card, config, client, cache_dir, force=force)
                console.print(f"[green]Pulled card: {escape(result.title)} [{result.uid6}][/green]")
            elif list_name:
                cards = pull_list(list_name, config, client, cache_dir, force=force)
                # Resolve display name: if user passed a raw ID, look up the name
                from trache.cache.index import resolve_list_id, resolve_list_name

                if len(list_name) == 24:
                    display_name = resolve_list_name(list_name, cache_dir / "indexes")
                else:
                    display_name = list_name
                console.print(
                    f'[green]Pulled {len(cards)} cards from list "{escape(display_name)}"[/green]'
                )
            else:
                result = pull_full_board(config, client, cache_dir, force=force)
                if result is None:
                    console.print("Already up to date.")
                else:
                    console.print(
                        f"[green]Pulled {escape(result.board_name)}: "
                        f"{result.cards} cards, {result.lists} lists, "
                        f"{result.labels} labels, {result.checklists} checklists[/green]"
                    )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except KeyError as e:
        msg = e.args[0] if e.args else "Requested item not found"
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show dirty state summary (modified/added/deleted)."""
    from trache.cache.diff import compute_diff

    if not TRACHE_ROOT.exists():
        console.print("Clean — no local changes.")
        return
    try:
        cache_dir = resolve_cache_dir()
    except FileNotFoundError:
        console.print("Clean — no local changes.")
        return
    changeset = compute_diff(cache_dir)

    if changeset.is_empty:
        console.print("Clean — no local changes.")
        return

    if changeset.added:
        console.print(f"[green]  Added: {len(changeset.added)}[/green]")
        for c in changeset.added:
            suffix = f" ({', '.join(c.annotations)})" if c.annotations else ""
            console.print(f"    + {escape(c.title)}{suffix}")

    if changeset.modified:
        console.print(f"[yellow]  Modified: {len(changeset.modified)}[/yellow]")
        for c in changeset.modified:
            fields = ", ".join(c.field_changes.keys())
            console.print(f"    ~ {c.title} ({fields})")

    if changeset.deleted:
        console.print(f"[red]  Deleted: {len(changeset.deleted)}[/red]")
        for c in changeset.deleted:
            console.print(f"    - {c.title}")

    if changeset.label_changes:
        created = [lc for lc in changeset.label_changes if lc.change_type == "created"]
        deleted = [lc for lc in changeset.label_changes if lc.change_type == "deleted"]
        if created:
            console.print(f"[green]  Labels created: {len(created)}[/green]")
            for lc in created:
                console.print(f"    + {lc.label_name} ({lc.label_color or 'no color'})")
        if deleted:
            console.print(f"[red]  Labels deleted: {len(deleted)}[/red]")
            for lc in deleted:
                console.print(f"    - {lc.label_name}")


@app.command()
def diff() -> None:
    """Show detailed diff between clean and working copy."""
    from trache.cache.diff import compute_diff, format_diff

    cache_dir = resolve_cache_dir()
    changeset = compute_diff(cache_dir)
    console.print(format_diff(changeset))


@app.command()
def push(
    card: Optional[str] = typer.Option(None, "--card", "-c", help="Push single card (ID or UID6)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be pushed without pushing"
    ),
) -> None:
    """Push local changes to Trello."""
    from trache.sync.push import push_changes

    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    def _progress(current: int, total: int, desc: str) -> None:
        console.print(f"[dim]  [{current}/{total}] {desc}[/dim]")

    try:
        with client:
            changeset, result = push_changes(
                config, client, cache_dir, dry_run=dry_run, card_filter=card,
                on_progress=_progress,
            )
    except KeyError as e:
        msg = e.args[0] if e.args else "Requested item not found"
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    if changeset.is_empty:
        console.print("Nothing to push.")
        return

    if dry_run:
        console.print("[yellow]Dry run — would push:[/yellow]")
    else:
        console.print(
            f"[green]Pushed {result.total} "
            f"change{'s' if result.total != 1 else ''}:[/green]"
        )

    for entry in result.pushed:
        fields = f" ({', '.join(entry.fields)})" if entry.fields else ""
        console.print(f"  ~ {escape(entry.title)} [{entry.uid6}]{fields}")
    for entry in result.created:
        id_info = f"{entry.old_uid6} → {entry.uid6}" if not dry_run else entry.uid6
        suffix = " (archived)" if entry.also_archived else ""
        console.print(f"  + {escape(entry.title)} [{id_info}]{suffix}")
    for entry in result.archived:
        console.print(f"  - {escape(entry.title)} [{entry.uid6}]")

    if result.errors:
        for err in result.errors:
            console.print(f"[red]Error: {err}[/red]")
        console.print("[dim]Run `trache status` to see remaining dirty cards.[/dim]")
        raise typer.Exit(1)


@app.command()
def sync(
    card: Optional[str] = typer.Option(
        None, "--card", "-c", help="Sync single card (push then pull one card)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced"),
) -> None:
    """Push local changes then pull latest from Trello."""
    from trache.sync.pull import pull_card, pull_full_board
    from trache.sync.push import push_changes

    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    with client:
        # Push first
        changeset, result = push_changes(
            config, client, cache_dir, dry_run=dry_run, card_filter=card,
        )
        if not changeset.is_empty:
            console.print(f"Pushed {result.total} changes")
            if result.errors:
                for err in result.errors:
                    console.print(f"[red]Error: {err}[/red]")
                console.print(
                    "[red]Push had errors — skipping pull to preserve local state[/red]"
                )
                raise typer.Exit(1)

        # Only pull if no errors
        if not dry_run:
            if card:
                pull_result = pull_card(card, config, client, cache_dir, force=True)
                console.print(
                    f"[green]Pulled card: {escape(pull_result.title)} [{pull_result.uid6}][/green]"
                )
            else:
                pull_result = pull_full_board(config, client, cache_dir, force=True)
                if pull_result is None:
                    console.print("Already up to date.")
                else:
                    console.print(
                        f"[green]Pulled {escape(pull_result.board_name)}: "
                        f"{pull_result.cards} cards, {pull_result.lists} lists, "
                        f"{pull_result.labels} labels, {pull_result.checklists} checklists[/green]"
                    )
        else:
            console.print("[yellow]Dry run — skipping pull[/yellow]")


@app.command()
def agents(
    reference: bool = typer.Option(
        False, "--reference", help="Print on-demand command/workflow reference"
    ),
) -> None:
    """Print AI agent setup instructions or command reference."""
    from trache.cli.agents import print_install_block, print_reference_block

    if reference:
        print_reference_block()
    else:
        # Try to load board name from config for context
        board_name = None
        try:
            from trache.config import TracheConfig

            cache_dir = resolve_cache_dir()
            cfg = TracheConfig.load(cache_dir)
            board_name = getattr(cfg, "board_name", None)
        except Exception:
            pass
        print_install_block(board_name=board_name)


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"trache {__version__}")


if __name__ == "__main__":
    app()
