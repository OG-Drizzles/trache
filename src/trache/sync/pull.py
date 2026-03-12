"""Pull: fetch from Trello → overwrite clean + working + indexes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trache.api.client import TrelloClient
from trache.cache.index import build_card_indexes, build_list_index
from trache.cache.models import Card, Checklist
from trache.cache.snapshot import write_clean_snapshot
from trache.cache.store import write_card_file
from trache.config import SyncState, TracheConfig
from trache.identity import strip_block


def pull_full_board(config: TracheConfig, client: TrelloClient, cache_dir: Path) -> int:
    """Pull entire board: lists, cards, checklists → clean + working + indexes.

    Returns the number of cards pulled.
    """
    board_id = config.board_id

    # Fetch all data
    board = client.get_board(board_id)
    lists = client.get_board_lists(board_id)
    cards = client.get_board_cards(board_id)
    checklists = client.get_board_checklists(board_id)
    labels = client.get_board_labels(board_id)

    # Strip identity blocks from descriptions
    for card in cards:
        card.description = strip_block(card.description)

    # Attach checklists to cards
    _attach_checklists(cards, checklists)

    # Write board metadata
    board_meta = f"# {board.name}\n\n- **Board ID:** {board.id}\n- **URL:** {board.url}\n"
    (cache_dir / "clean" / "board_meta.md").write_text(board_meta)
    (cache_dir / "working" / "board_meta.md").write_text(board_meta)

    # Write labels
    labels_data = [{"id": lb.id, "name": lb.name, "color": lb.color} for lb in labels]
    labels_json = json.dumps(labels_data, indent=2) + "\n"
    (cache_dir / "clean" / "labels.json").write_text(labels_json)
    (cache_dir / "working" / "labels.json").write_text(labels_json)

    # Write checklists
    checklist_dir = cache_dir / "checklists"
    checklist_dir.mkdir(parents=True, exist_ok=True)
    for cl in checklists:
        cl_path = checklist_dir / f"{cl.id}.json"
        cl_path.write_text(cl.model_dump_json(indent=2) + "\n")

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

    # Build indexes
    index_dir = cache_dir / "indexes"
    build_card_indexes(cards, index_dir)
    build_list_index(lists, index_dir)

    # Update sync state
    state = SyncState(
        last_pull=datetime.now(timezone.utc).isoformat(),
        card_timestamps={
            c.id: c.last_activity.isoformat() if c.last_activity else ""
            for c in cards
        },
    )
    state.save(cache_dir)

    return len(cards)


def pull_card(
    card_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
) -> Card:
    """Pull a single card by ID."""
    from trache.cache.index import resolve_card_id

    card_id = resolve_card_id(card_identifier, cache_dir / "indexes")
    card = client.get_card(card_id)
    card.description = strip_block(card.description)

    # Fetch checklists for this card
    checklists = client.get_card_checklists(card_id)
    card.checklists = checklists

    # Write to clean and working
    write_card_file(card, cache_dir / "clean" / "cards")
    write_card_file(card, cache_dir / "working" / "cards")

    # Write checklists
    for cl in checklists:
        cl_path = cache_dir / "checklists" / f"{cl.id}.json"
        cl_path.write_text(cl.model_dump_json(indent=2) + "\n")

    # Rebuild indexes (incremental would be better but full rebuild is safe)
    from trache.cache.store import list_card_files, read_card_file

    all_cards = [read_card_file(p) for p in list_card_files(cache_dir / "clean" / "cards")]
    build_card_indexes(all_cards, cache_dir / "indexes")

    return card


def pull_list(
    list_identifier: str,
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
) -> list[Card]:
    """Pull all cards in a specific list."""
    from trache.cache.index import resolve_list_id

    list_id = resolve_list_id(list_identifier, cache_dir / "indexes")
    cards = client.get_list_cards(list_id)

    for card in cards:
        card.description = strip_block(card.description)
        checklists = client.get_card_checklists(card.id)
        card.checklists = checklists

        write_card_file(card, cache_dir / "clean" / "cards")
        write_card_file(card, cache_dir / "working" / "cards")

        for cl in checklists:
            cl_path = cache_dir / "checklists" / f"{cl.id}.json"
            cl_path.write_text(cl.model_dump_json(indent=2) + "\n")

    # Rebuild indexes
    from trache.cache.store import list_card_files, read_card_file

    all_cards = [read_card_file(p) for p in list_card_files(cache_dir / "clean" / "cards")]
    build_card_indexes(all_cards, cache_dir / "indexes")

    return cards


def _attach_checklists(cards: list[Card], checklists: list[Checklist]) -> None:
    """Attach checklists to their parent cards."""
    by_card: dict[str, list[Checklist]] = {}
    for cl in checklists:
        by_card.setdefault(cl.card_id, []).append(cl)
    for card in cards:
        card.checklists = by_card.get(card.id, [])
