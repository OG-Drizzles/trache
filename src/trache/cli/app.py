"""Typer app root: init, pull, push, sync, status, diff."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import os

import httpx
import typer
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
from trache.cli._output import get_output
from trache.cli.batch import batch_app
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
app.add_typer(batch_app, name="batch", help="Batch operations")
app.add_typer(board_app, name="board", help="Board management")
app.add_typer(card_app, name="card", help="Card operations")
app.add_typer(checklist_app, name="checklist", help="Checklist operations")
app.add_typer(comment_app, name="comment", help="Comment operations")
app.add_typer(label_app, name="label", help="Label operations")
app.add_typer(list_app, name="list", help="List operations")


@app.callback()
def main(
    board: Optional[str] = typer.Option(
        None, "--board", "-B", help="Board alias to operate on"
    ),
) -> None:
    """Local-first Trello cache with Git-style sync."""
    from trache.api.client import reset_api_stats

    reset_api_stats()
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

    out = get_output()

    # --new and --board-id/--board-url are mutually exclusive
    if new and (board_id or board_url):
        out.error("Cannot use --new with --board-id or --board-url")
        raise typer.Exit(1)

    config = TracheConfig(board_id=board_id or "pending")

    # Detect auth state from env vars
    api_key_val = os.environ.get(config.api_key_env)
    token_val = os.environ.get(config.token_env)
    auth_configured = bool(api_key_val and token_val)

    # Handle --new: create board on Trello
    if new:
        if not auth_configured:
            out.error("Auth must be configured to create a board. Set TRELLO_API_KEY and TRELLO_TOKEN.")
            raise typer.Exit(1)

        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth_obj = TrelloAuth.from_env(config.api_key_env, config.token_env)
        with TrelloClient(auth_obj) as client:
            board_obj = client.create_board(new)
            board_id = board_obj.id
            config.board_id = board_id
            config.board_name = board_obj.name
            out.human(f"[green]Created board: {board_obj.name} on Trello[/green]")

    if not board_id and not board_url and not new:
        board_id = typer.prompt("Board ID")

    if board_url and not board_id:
        parts = board_url.rstrip("/").split("/")
        try:
            b_idx = parts.index("b")
            board_id = parts[b_idx + 1]
        except (ValueError, IndexError):
            out.error("Could not extract board ID from URL")
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

    # Token validation and board name fetch
    if not new:
        if not auth_configured:
            out.human(
                "[yellow]Auth not configured — skipping board name fetch and token validation.[/yellow]"
            )
        else:
            from trache.api.auth import TrelloAuth
            from trache.api.client import TrelloClient

            auth_obj = TrelloAuth.from_env(config.api_key_env, config.token_env)
            with TrelloClient(auth_obj) as client:
                try:
                    member = client.get_current_member()
                    member_name = member.get("fullName") or member.get("username", "unknown")
                    out.human(f"[green]Token valid — authenticated as {member_name}[/green]")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        out.human("[red]Token validation failed (401 Unauthorized)[/red]")
                    else:
                        raise

                try:
                    board_obj = client.get_board(config.board_id)
                    config.board_name = board_obj.name
                    out.human(f"Board: [bold]{board_obj.name}[/bold]")
                except Exception:
                    out.human("[yellow]Could not fetch board name[/yellow]")

    # Determine alias
    alias = name
    if not alias:
        alias = slugify(config.board_name) if config.board_name else slugify(config.board_id[:12])

    # Check for alias collision
    existing = list_board_names()
    if alias in existing:
        out.error(f"Board alias '{alias}' already exists. Use --name to choose a different alias.")
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

    if out.is_human:
        out.human(f"[green]Initialised board '{alias}' for {config.board_id}[/green]")
    else:
        out.json({"ok": True, "alias": alias, "board_id": config.board_id})

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

    out = get_output()
    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    try:
        with client:
            if card:
                result = pull_card(card, config, client, cache_dir, force=force)
                if out.is_human:
                    out.human(f"[green]Pulled card: {escape(result.title)} [{result.uid6}][/green]")
                else:
                    out.json({
                        "uid6": result.uid6, "title": result.title,
                        "list": result.list_id, "description": result.description,
                    })
            elif list_name:
                cards = pull_list(list_name, config, client, cache_dir, force=force)
                if out.is_human:
                    from trache.cache.db import resolve_list_name
                    if len(list_name) == 24:
                        display_name = resolve_list_name(list_name, cache_dir)
                    else:
                        display_name = list_name
                    out.human(
                        f'[green]Pulled {len(cards)} cards from list "{escape(display_name)}"[/green]'
                    )
                else:
                    out.json({
                        "cards": len(cards),
                        "card_summaries": [
                            {"uid6": c.uid6, "title": c.title, "list": c.list_id}
                            for c in cards
                        ],
                    })
            else:
                result = pull_full_board(config, client, cache_dir, force=force)
                if result is None:
                    if out.is_human:
                        out.human("Already up to date.")
                    else:
                        out.json({"up_to_date": True})
                else:
                    if out.is_human:
                        out.human(
                            f"[green]Pulled {escape(result.board_name)}: "
                            f"{result.cards} cards, {result.lists} lists, "
                            f"{result.labels} labels, {result.checklists} checklists[/green]"
                        )
                    else:
                        out.json({
                            "board_name": result.board_name,
                            "cards": result.cards,
                            "lists": result.lists,
                            "labels": result.labels,
                            "checklists": result.checklists,
                            "card_summaries": [
                                {"uid6": s.uid6, "title": s.title, "list": s.list_name}
                                for s in result.card_summaries
                            ],
                            "list_summaries": [
                                {"name": s.name} for s in result.list_summaries
                            ],
                        })
    except RuntimeError as e:
        out.error(str(e))
        raise typer.Exit(1)
    except KeyError as e:
        msg = e.args[0] if e.args else "Requested item not found"
        out.error(msg)
        raise typer.Exit(1)

    out.api_stats()


@app.command()
def status() -> None:
    """Show dirty state summary (modified/added/deleted)."""
    from trache.cache.diff import compute_diff, serialise_changeset

    out = get_output()

    if not TRACHE_ROOT.exists():
        if out.is_human:
            out.human("Clean — no local changes.")
        else:
            out.json({"added": [], "modified": [], "deleted": []})
        return
    try:
        cache_dir = resolve_cache_dir()
    except FileNotFoundError:
        if out.is_human:
            out.human("Clean — no local changes.")
        else:
            out.json({"added": [], "modified": [], "deleted": []})
        return
    changeset = compute_diff(cache_dir)

    if not out.is_human:
        out.json(serialise_changeset(changeset))
        return

    if changeset.is_empty:
        out.human("Clean — no local changes.")
        return

    if changeset.added:
        out.human(f"[green]  Added: {len(changeset.added)}[/green]")
        for c in changeset.added:
            suffix = f" ({', '.join(c.annotations)})" if c.annotations else ""
            out.human(f"    + {escape(c.title)}{suffix}")

    if changeset.modified:
        out.human(f"[yellow]  Modified: {len(changeset.modified)}[/yellow]")
        for c in changeset.modified:
            fields = ", ".join(c.field_changes.keys())
            out.human(f"    ~ {c.title} ({fields})")

    if changeset.deleted:
        out.human(f"[red]  Deleted: {len(changeset.deleted)}[/red]")
        for c in changeset.deleted:
            out.human(f"    - {c.title}")

    if changeset.label_changes:
        created = [lc for lc in changeset.label_changes if lc.change_type == "created"]
        deleted = [lc for lc in changeset.label_changes if lc.change_type == "deleted"]
        if created:
            out.human(f"[green]  Labels created: {len(created)}[/green]")
            for lc in created:
                out.human(f"    + {lc.label_name} ({lc.label_color or 'no color'})")
        if deleted:
            out.human(f"[red]  Labels deleted: {len(deleted)}[/red]")
            for lc in deleted:
                out.human(f"    - {lc.label_name}")


@app.command()
def diff() -> None:
    """Show detailed diff between clean and working copy."""
    from trache.cache.diff import compute_diff, format_diff, serialise_changeset

    out = get_output()
    cache_dir = resolve_cache_dir()
    changeset = compute_diff(cache_dir)

    if out.is_human:
        out.human(format_diff(changeset))
    else:
        out.json(serialise_changeset(changeset))


@app.command()
def stale() -> None:
    """Check if the board has remote changes since the last pull."""
    from trache.sync.pull import check_staleness

    out = get_output()
    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    with client:
        result = check_staleness(config, client, cache_dir)

    if out.is_human:
        if result.is_stale:
            out.human("Board has remote changes — run `trache pull`.")
        else:
            out.human("Board is up to date.")
    else:
        out.json({
            "stale": result.is_stale,
            "local_activity": result.local_activity,
            "remote_activity": result.remote_activity,
        })

    out.api_stats()


@app.command()
def push(
    card: Optional[str] = typer.Option(None, "--card", "-c", help="Push single card (ID or UID6)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be pushed without pushing"
    ),
) -> None:
    """Push local changes to Trello."""
    from trache.sync.push import push_changes

    out = get_output()
    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    def _progress(current: int, total: int, desc: str) -> None:
        out.human(f"[dim]  [{current}/{total}] {desc}[/dim]")

    try:
        with client:
            changeset, result = push_changes(
                config, client, cache_dir, dry_run=dry_run, card_filter=card,
                on_progress=_progress,
            )
    except KeyError as e:
        msg = e.args[0] if e.args else "Requested item not found"
        out.error(msg)
        raise typer.Exit(1)

    if not out.is_human:
        out.json(_serialise_push_result(result))
        if result.errors:
            raise typer.Exit(1)
        return

    if changeset.is_empty:
        out.human("Nothing to push.")
        return

    if dry_run:
        out.human("[yellow]Dry run — would push:[/yellow]")
    else:
        out.human(
            f"[green]Pushed {result.total} "
            f"change{'s' if result.total != 1 else ''}:[/green]"
        )

    for entry in result.pushed:
        fields = f" ({', '.join(entry.fields)})" if entry.fields else ""
        out.human(f"  ~ {escape(entry.title)} [{entry.uid6}]{fields}")
    for entry in result.created:
        id_info = f"{entry.old_uid6} → {entry.uid6}" if not dry_run else entry.uid6
        suffix = " (archived)" if entry.also_archived else ""
        out.human(f"  + {escape(entry.title)} [{id_info}]{suffix}")
    for entry in result.archived:
        out.human(f"  - {escape(entry.title)} [{entry.uid6}]")

    out.api_stats()

    if result.errors:
        for err in result.errors:
            out.human(f"[red]Error: {err}[/red]")
        out.human("[dim]Run `trache status` to see remaining dirty cards.[/dim]")
        raise typer.Exit(1)


def _serialise_push_result(result) -> dict:
    """Convert a PushResult to a JSON-serialisable dict."""
    return {
        "total": result.total,
        "pushed": [
            {"uid6": e.uid6, "title": e.title, "fields": e.fields}
            for e in result.pushed
        ],
        "created": [
            {"uid6": e.uid6, "title": e.title, "old_uid6": e.old_uid6}
            for e in result.created
        ],
        "archived": [
            {"uid6": e.uid6, "title": e.title}
            for e in result.archived
        ],
        "errors": result.errors,
    }


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

    out = get_output()
    cache_dir = resolve_cache_dir()
    client, config = _get_client(cache_dir)

    with client:
        # Push first
        changeset, result = push_changes(
            config, client, cache_dir, dry_run=dry_run, card_filter=card,
        )

        push_data = _serialise_push_result(result)

        if not changeset.is_empty:
            out.human(f"Pushed {result.total} changes")
            if result.errors:
                for err in result.errors:
                    out.error(err)
                if not out.is_human:
                    out.json({"ok": False, "stage": "push", "push": push_data, "pull": None})
                else:
                    out.error("Push had errors — skipping pull to preserve local state")
                raise typer.Exit(1)

        # Only pull if no errors
        pull_data: dict | None = None
        if not dry_run:
            if card:
                pull_result = pull_card(card, config, client, cache_dir, force=True)
                out.human(
                    f"[green]Pulled card: {escape(pull_result.title)} [{pull_result.uid6}][/green]"
                )
                pull_data = {
                    "uid6": pull_result.uid6, "title": pull_result.title,
                    "list": pull_result.list_id, "description": pull_result.description,
                }
            else:
                pull_result = pull_full_board(config, client, cache_dir, force=True)
                if pull_result is None:
                    out.human("Already up to date.")
                    pull_data = {"up_to_date": True}
                else:
                    out.human(
                        f"[green]Pulled {escape(pull_result.board_name)}: "
                        f"{pull_result.cards} cards, {pull_result.lists} lists, "
                        f"{pull_result.labels} labels, {pull_result.checklists} checklists[/green]"
                    )
                    pull_data = {
                        "board_name": pull_result.board_name,
                        "cards": pull_result.cards,
                        "lists": pull_result.lists,
                        "labels": pull_result.labels,
                        "checklists": pull_result.checklists,
                    }
        else:
            out.human("[yellow]Dry run — skipping pull[/yellow]")

    if not out.is_human:
        out.json({"ok": True, "dry_run": dry_run, "push": push_data, "pull": pull_data})

    out.api_stats()


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
    out = get_output()
    if out.is_human:
        out.human(f"trache {__version__}")
    else:
        out.tsv([[f"trache", __version__]], header=["name", "version"])


if __name__ == "__main__":
    app()
