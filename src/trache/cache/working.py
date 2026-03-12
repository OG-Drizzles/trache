"""Working copy mutations — local edits before push."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from trache.cache.index import resolve_card_id, resolve_list_id
from trache.cache.models import Card
from trache.cache.store import list_card_files, read_card_file, write_card_file


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _working_dir(cache_dir: Path) -> Path:
    return cache_dir / "working" / "cards"


def _index_dir(cache_dir: Path) -> Path:
    return cache_dir / "indexes"


def read_working_card(identifier: str, cache_dir: Path) -> Card:
    """Read a card from the working copy by ID or UID6."""
    card_id = resolve_card_id(identifier, _index_dir(cache_dir))
    path = _working_dir(cache_dir) / f"{card_id}.md"
    return read_card_file(path)


def list_working_cards(cache_dir: Path) -> list[Card]:
    """Read all cards from the working copy."""
    return [read_card_file(p) for p in list_card_files(_working_dir(cache_dir))]


def edit_title(identifier: str, new_title: str, cache_dir: Path) -> Card:
    """Edit a card's title in the working copy."""
    card = read_working_card(identifier, cache_dir)
    card.title = new_title
    card.content_modified_at = _now()
    card.dirty = True
    write_card_file(card, _working_dir(cache_dir))
    return card


def edit_description(identifier: str, new_desc: str, cache_dir: Path) -> Card:
    """Edit a card's description in the working copy."""
    card = read_working_card(identifier, cache_dir)
    card.description = new_desc
    card.content_modified_at = _now()
    card.dirty = True
    write_card_file(card, _working_dir(cache_dir))
    return card


def move_card(identifier: str, list_identifier: str, cache_dir: Path) -> Card:
    """Move a card to a different list in the working copy."""
    card = read_working_card(identifier, cache_dir)
    new_list_id = resolve_list_id(list_identifier, _index_dir(cache_dir))
    card.list_id = new_list_id
    card.content_modified_at = _now()
    card.dirty = True
    write_card_file(card, _working_dir(cache_dir))
    return card


def create_card(
    list_identifier: str,
    title: str,
    cache_dir: Path,
    board_id: str,
    description: str = "",
) -> Card:
    """Create a new card in the working copy."""
    list_id = resolve_list_id(list_identifier, _index_dir(cache_dir))

    # Generate a temporary ID for new cards (will be replaced on push)
    temp_id = f"new_{uuid4().hex[:18]}"

    card = Card(
        id=temp_id,
        board_id=board_id,
        list_id=list_id,
        title=title,
        description=description,
        created_at=_now(),
        content_modified_at=_now(),
        last_activity=_now(),
        dirty=True,
    )
    write_card_file(card, _working_dir(cache_dir))
    return card


def archive_card(identifier: str, cache_dir: Path) -> Card:
    """Archive a card in the working copy."""
    card = read_working_card(identifier, cache_dir)
    card.closed = True
    card.content_modified_at = _now()
    card.dirty = True
    write_card_file(card, _working_dir(cache_dir))
    return card
