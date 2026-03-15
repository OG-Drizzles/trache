"""Pull: fetch from Trello → overwrite clean + working + indexes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from trache.api.client import TrelloClient
from trache.cache.db import (
    connect,
    delete_card,
    list_cards,
    read_card,
    read_checklists,
    resolve_card_id,
    resolve_list_id,
    write_card,
    write_card_pull,
    write_cards_batch,
    write_checklists,
    write_full_snapshot,
    write_labels,
    write_lists,
)
from trache.cache.diff import fields_equal
from trache.cache.models import Card, Checklist, Label
from trache.config import SyncState, TracheConfig
from trache.identity import strip_block

_CONTENT_FIELDS = ("title", "description", "list_id", "labels", "due", "closed")


@dataclass
class StalenessResult:
    """Result of a staleness check."""

    is_stale: bool
    local_activity: str | None
    remote_activity: str | None


@dataclass
class CardSummary:
    uid6: str
    title: str
    list_name: str


@dataclass
class ListSummary:
    name: str


@dataclass
class PullResult:
    """Result of a full board pull with counts and summaries for display."""

    board_name: str
    cards: int
    lists: int
    labels: int
    checklists: int
    card_summaries: list[CardSummary] = field(default_factory=list)
    list_summaries: list[ListSummary] = field(default_factory=list)


def _check_dirty_state(cache_dir: Path, force: bool) -> None:
    """Refuse to overwrite dirty working state unless force=True."""
    from trache.cache.diff import compute_diff

    changeset = compute_diff(cache_dir)
    if not changeset.is_empty and not force:
        raise RuntimeError(
            "Working copy has unpushed changes. Push first or use --force to override."
        )


def _check_card_dirty(card_id: str, cache_dir: Path, force: bool) -> None:
    """Refuse to overwrite a single card if it has unpushed changes (unless force=True)."""
    if force:
        return

    try:
        clean_card = read_card(card_id, "clean", cache_dir)
        working_card = read_card(card_id, "working", cache_dir)
    except FileNotFoundError:
        return  # New card or missing — no conflict

    if any(
        not fields_equal(f, getattr(clean_card, f), getattr(working_card, f))
        for f in _CONTENT_FIELDS
    ):
        uid6 = card_id[-6:].upper()
        raise RuntimeError(
            f"Card {uid6} has unpushed changes. "
            f"Push first or use --force to override."
        )


def check_staleness(
    config: TracheConfig, client: TrelloClient, cache_dir: Path
) -> StalenessResult:
    """Check if the board has remote changes since the last pull. One cheap API call."""
    board = client.get_board(config.board_id)
    state = SyncState.load(cache_dir)

    remote = board.date_last_activity.isoformat() if board.date_last_activity else None
    local = state.board_last_activity

    is_stale = remote != local if (remote is not None and local is not None) else True
    return StalenessResult(is_stale=is_stale, local_activity=local, remote_activity=remote)


def pull_full_board(
    config: TracheConfig, client: TrelloClient, cache_dir: Path, *, force: bool = False
) -> Optional[PullResult]:
    """Pull entire board: lists, cards, checklists → clean + working + indexes."""
    _check_dirty_state(cache_dir, force)

    board_id = config.board_id
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
    all_checklists = client.get_board_checklists(board_id)
    labels_list = client.get_board_labels(board_id)

    # Strip identity blocks from descriptions
    for card in cards:
        card.description = strip_block(card.description)

    # Attach checklists to cards
    _attach_checklists(cards, all_checklists)

    # Preserve content_modified_at for unchanged content
    for card in cards:
        _preserve_content_modified_at(card, cache_dir)

    # Convert labels to Label models
    label_models = [Label(id=lb.id, name=lb.name, color=lb.color) for lb in labels_list]

    # Atomic full-board write
    write_full_snapshot(cards, all_checklists, lists, label_models, cache_dir)

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

    # Build list name lookup for summaries
    list_name_map = {lst.id: lst.name for lst in lists}

    return PullResult(
        board_name=board.name,
        cards=len(cards),
        lists=len(lists),
        labels=len(labels_list),
        checklists=len(all_checklists),
        card_summaries=[
            CardSummary(uid6=c.uid6, title=c.title, list_name=list_name_map.get(c.list_id, c.list_id))
            for c in cards
        ],
        list_summaries=[ListSummary(name=lst.name) for lst in lists],
    )


def pull_card(
    card_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
    *,
    force: bool = False,
    _skip_dirty_check: bool = False,
) -> Card:
    """Pull a single card by ID."""
    card_id = resolve_card_id(card_identifier, cache_dir)

    # Scoped dirty guard: only check THIS card, not the whole board
    if not _skip_dirty_check:
        _check_card_dirty(card_id, cache_dir, force)

    try:
        card = client.get_card(card_id)
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "not found" in err_str.lower():
            raise KeyError(
                f"Card {card_identifier} not found on Trello (may have been deleted). "
                f"Use `trache pull` to refresh the full board."
            )
        raise
    card.description = strip_block(card.description)

    # Fetch checklists for this card
    card_checklists = client.get_card_checklists(card_id)
    card.checklists = card_checklists

    # Preserve content_modified_at for unchanged content
    _preserve_content_modified_at(card, cache_dir)

    # Atomic write: card + checklists to both clean and working in one transaction
    with connect(cache_dir) as conn:
        write_card_pull(card, card_checklists, cache_dir, conn=conn)
        # If card is archived/closed, remove from working so it doesn't appear in card list
        if card.closed:
            conn.execute("DELETE FROM cards WHERE id = ? AND copy = 'working'", (card_id,))
            conn.execute("DELETE FROM checklist_items WHERE card_id = ? AND copy = 'working'", (card_id,))
            conn.execute("DELETE FROM checklists WHERE card_id = ? AND copy = 'working'", (card_id,))

    # Update card_timestamps for this card
    state = SyncState.load(cache_dir)
    state.card_timestamps[card.id] = card.last_activity.isoformat() if card.last_activity else ""
    state.save(cache_dir)

    return card


def pull_list(
    list_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
    *,
    force: bool = False,
) -> list[Card]:
    """Pull all cards in a specific list."""
    list_id = resolve_list_id(list_identifier, cache_dir)
    cards = client.get_list_cards(list_id)

    # Scoped dirty guard: check each card individually
    if not force:
        for card in cards:
            _check_card_dirty(card.id, cache_dir, force)

    # Fetch checklists per card
    all_checklists: list[Checklist] = []
    for card in cards:
        card_cls = client.get_card_checklists(card.id)
        all_checklists.extend(card_cls)

    # Attach checklists to cards
    _attach_checklists(cards, all_checklists)

    # Pre-compute checklists by card
    cls_by_card: dict[str, list[Checklist]] = {}
    for cl in all_checklists:
        cls_by_card.setdefault(cl.card_id, []).append(cl)

    # Atomic write: all cards + checklists in one transaction
    for card in cards:
        card.description = strip_block(card.description)
        _preserve_content_modified_at(card, cache_dir)

    with connect(cache_dir) as conn:
        for card in cards:
            card_cls = cls_by_card.get(card.id, [])
            write_card_pull(card, card_cls, cache_dir, conn=conn)

    # Update card_timestamps for all pulled cards in bulk
    state = SyncState.load(cache_dir)
    for card in cards:
        state.card_timestamps[card.id] = (
            card.last_activity.isoformat() if card.last_activity else ""
        )
    state.save(cache_dir)

    return cards


def _preserve_content_modified_at(new_card: Card, cache_dir: Path) -> None:
    """Preserve content_modified_at if content hasn't changed vs clean snapshot."""
    try:
        old_card = read_card(new_card.id, "clean", cache_dir)
    except FileNotFoundError:
        return  # First pull — keep dateLastActivity as default

    content_changed = any(
        not fields_equal(f, getattr(old_card, f), getattr(new_card, f))
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
