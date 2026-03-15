"""Pull: fetch from Trello → overwrite clean + working + indexes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from trache.api.client import TrelloClient
from trache.cache.diff import _fields_equal
from trache.cache.index import add_card_to_index, build_index
from trache.cache.models import Card, Checklist
from trache.cache.snapshot import write_clean_snapshot
from trache.cache.store import read_card_file, write_card_file
from trache.config import SyncState, TracheConfig
from trache.identity import strip_block


@dataclass
class PullResult:
    """Result of a full board pull with counts for display."""

    board_name: str
    cards: int
    lists: int
    labels: int
    checklists: int


def _check_dirty_state(cache_dir: Path, force: bool) -> None:
    """Refuse to overwrite dirty working state unless force=True."""
    from trache.cache.diff import compute_diff

    changeset = compute_diff(cache_dir)
    if not changeset.is_empty and not force:
        raise RuntimeError(
            "Working copy has unpushed changes. Push first or use --force to override."
        )


def pull_full_board(
    config: TracheConfig, client: TrelloClient, cache_dir: Path, *, force: bool = False
) -> Optional[PullResult]:
    """Pull entire board: lists, cards, checklists → clean + working + indexes.

    Returns a PullResult with counts for display.
    Raises RuntimeError if working copy has unpushed changes and force=False.
    """
    _check_dirty_state(cache_dir, force)
    board_id = config.board_id

    # Fetch board metadata (cheap call)
    board = client.get_board(board_id)

    # Stale check: skip full pull if board hasn't changed
    if not force and board.date_last_activity is not None:
        state = SyncState.load(cache_dir)
        if (
            state.board_last_activity is not None
            and state.board_last_activity == board.date_last_activity.isoformat()
        ):
            return None  # Already up to date

    # Fetch all data
    lists = client.get_board_lists(board_id)
    cards = client.get_board_cards(board_id)
    checklists = client.get_board_checklists(board_id)
    labels = client.get_board_labels(board_id)

    # Strip identity blocks from descriptions
    for card in cards:
        card.description = strip_block(card.description)

    # Attach checklists to cards
    _attach_checklists(cards, checklists)

    # Preserve content_modified_at for unchanged content
    clean_cards_dir = cache_dir / "clean" / "cards"
    for card in cards:
        _preserve_content_modified_at(card, clean_cards_dir)

    # Write board metadata
    from trache.cache._atomic import atomic_write

    board_meta = f"# {board.name}\n\n- **Board ID:** {board.id}\n- **URL:** {board.url}\n"
    atomic_write(cache_dir / "clean" / "board_meta.md", board_meta)
    atomic_write(cache_dir / "working" / "board_meta.md", board_meta)

    # Write labels
    labels_data = [{"id": lb.id, "name": lb.name, "color": lb.color} for lb in labels]
    labels_json = json.dumps(labels_data, indent=2) + "\n"
    atomic_write(cache_dir / "clean" / "labels.json", labels_json)
    atomic_write(cache_dir / "working" / "labels.json", labels_json)

    # Write per-card checklist files to clean/working
    _write_per_card_checklists(checklists, cache_dir)

    # Clean up old checklists/ dir (migration from pre-0.1.1)
    old_cl_dir = cache_dir / "checklists"
    if old_cl_dir.exists():
        import shutil

        shutil.rmtree(old_cl_dir)

    # Write clean snapshot
    write_clean_snapshot(cards, cache_dir)

    # Write working copy (full overwrite on pull)
    working_dir = cache_dir / "working" / "cards"
    working_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale working files
    for f in working_dir.glob("*.md"):
        f.unlink()
    for card in cards:
        write_card_file(card, working_dir)

    # Build unified index
    index_dir = cache_dir / "indexes"
    build_index(cards, lists, index_dir)

    # Update sync state
    state = SyncState(
        last_pull=datetime.now(timezone.utc).isoformat(),
        board_last_activity=(
            board.date_last_activity.isoformat() if board.date_last_activity else None
        ),
        card_timestamps={
            c.id: c.last_activity.isoformat() if c.last_activity else ""
            for c in cards
        },
    )
    state.save(cache_dir)

    return PullResult(
        board_name=board.name,
        cards=len(cards),
        lists=len(lists),
        labels=len(labels),
        checklists=len(checklists),
    )


def pull_card(
    card_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
    *,
    force: bool = False,
) -> Card:
    """Pull a single card by ID.

    Raises RuntimeError if working copy has unpushed changes and force=False.
    """
    _check_dirty_state(cache_dir, force)
    from trache.cache.index import resolve_card_id

    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")
    try:
        card = client.get_card(card_id)
    except Exception as e:
        # Handle 404 (deleted remote card) gracefully
        err_str = str(e)
        if "404" in err_str or "not found" in err_str.lower():
            raise KeyError(
                f"Card {card_identifier} not found on Trello (may have been deleted). "
                f"Use `trache pull` to refresh the full board."
            )
        raise
    card.description = strip_block(card.description)

    # Fetch checklists for this card
    checklists = client.get_card_checklists(card_id)
    card.checklists = checklists

    # Preserve content_modified_at for unchanged content
    _preserve_content_modified_at(card, cache_dir / "clean" / "cards")

    # Write to clean and working
    write_card_file(card, cache_dir / "clean" / "cards")
    write_card_file(card, cache_dir / "working" / "cards")

    # Write per-card checklist files
    _write_per_card_checklists(checklists, cache_dir)

    # If card is archived/closed, remove from index so it doesn't appear in card list
    if card.closed:
        from trache.cache.index import remove_card_from_index

        remove_card_from_index(card_id, cache_dir / "indexes")
    else:
        add_card_to_index(card, cache_dir / "indexes")

    return card


def pull_list(
    list_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
    *,
    force: bool = False,
) -> list[Card]:
    """Pull all cards in a specific list.

    Raises RuntimeError if working copy has unpushed changes and force=False.
    """
    _check_dirty_state(cache_dir, force)
    from trache.cache.index import resolve_list_id

    list_id = resolve_list_id(list_identifier, cache_dir / "indexes")
    cards = client.get_list_cards(list_id)

    # Fetch all board checklists in one call instead of N+1 per-card calls
    card_ids = {card.id for card in cards}
    all_checklists = client.get_board_checklists(config.board_id)
    checklists_for_list = [cl for cl in all_checklists if cl.card_id in card_ids]

    # Attach checklists to cards
    _attach_checklists(cards, checklists_for_list)

    for card in cards:
        card.description = strip_block(card.description)

        # Preserve content_modified_at for unchanged content
        _preserve_content_modified_at(card, cache_dir / "clean" / "cards")

        write_card_file(card, cache_dir / "clean" / "cards")
        write_card_file(card, cache_dir / "working" / "cards")

    # Write per-card checklist files
    _write_per_card_checklists(checklists_for_list, cache_dir)

    # Incremental index update per card
    for card in cards:
        add_card_to_index(card, cache_dir / "indexes")

    return cards


def _write_per_card_checklists(checklists: list[Checklist], cache_dir: Path) -> None:
    """Write per-card checklist JSON files to clean and working directories."""
    checklists_by_card: dict[str, list[Checklist]] = {}
    for cl in checklists:
        checklists_by_card.setdefault(cl.card_id, []).append(cl)

    for card_id, card_cls in checklists_by_card.items():
        cl_data = [cl.model_dump() for cl in card_cls]
        cl_json = json.dumps(cl_data, indent=2, default=str) + "\n"
        clean_cl_dir = cache_dir / "clean" / "checklists"
        working_cl_dir = cache_dir / "working" / "checklists"
        clean_cl_dir.mkdir(parents=True, exist_ok=True)
        working_cl_dir.mkdir(parents=True, exist_ok=True)
        from trache.cache._atomic import atomic_write

        atomic_write(clean_cl_dir / f"{card_id}.json", cl_json)
        atomic_write(working_cl_dir / f"{card_id}.json", cl_json)


_CONTENT_FIELDS = ("title", "description", "list_id", "labels", "due", "closed")


def _preserve_content_modified_at(new_card: Card, clean_dir: Path) -> None:
    """Preserve content_modified_at if content hasn't changed vs clean snapshot."""
    clean_path = clean_dir / f"{new_card.id}.md"
    if not clean_path.exists():
        return  # First pull — keep dateLastActivity as default

    old_card = read_card_file(clean_path)
    content_changed = any(
        not _fields_equal(f, getattr(old_card, f), getattr(new_card, f))
        for f in _CONTENT_FIELDS
    )

    # Also compare checklists if present
    if not content_changed and new_card.checklists:
        old_items = {
            (item.id, item.name, item.state)
            for cl in old_card.checklists
            for item in cl.items
        }
        new_items = {
            (item.id, item.name, item.state)
            for cl in new_card.checklists
            for item in cl.items
        }
        content_changed = old_items != new_items

    if not content_changed:
        new_card.content_modified_at = old_card.content_modified_at


def _attach_checklists(cards: list[Card], checklists: list[Checklist]) -> None:
    """Attach checklists to their parent cards."""
    by_card: dict[str, list[Checklist]] = {}
    for cl in checklists:
        by_card.setdefault(cl.card_id, []).append(cl)
    for card in cards:
        card.checklists = by_card.get(card.id, [])
