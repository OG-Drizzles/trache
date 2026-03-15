"""Index operations — delegates to SQLite database.

All functions preserve their original signatures (accepting index_dir: Path)
for backward compatibility with callers. Internally they compute cache_dir
from index_dir (parent) and route to db.py.
"""

from __future__ import annotations

from pathlib import Path

from trache.cache.models import Card, TrelloList

INDEX_FILENAME = "index.json"  # kept for migration detection


def _cache_dir_from_index_dir(index_dir: Path) -> Path:
    """Compute cache_dir from the old-style index_dir path.

    Callers pass `cache_dir / "indexes"` — we strip the last component.
    If index_dir doesn't end with "indexes", assume it IS the cache_dir.
    """
    if index_dir.name == "indexes":
        return index_dir.parent
    return index_dir


def build_index(
    cards: list[Card], lists: list[TrelloList], index_dir: Path
) -> None:
    """Build the unified discovery index (writes cards to working + lists)."""
    from trache.cache.db import write_cards_batch, write_lists

    cache_dir = _cache_dir_from_index_dir(index_dir)
    write_cards_batch(cards, "working", cache_dir)
    write_lists(lists, cache_dir)


def build_card_indexes(cards: list[Card], index_dir: Path) -> None:
    """Rebuild card sections of the index, preserving lists."""
    from trache.cache.db import write_cards_batch

    cache_dir = _cache_dir_from_index_dir(index_dir)
    write_cards_batch(cards, "working", cache_dir)


def build_list_index(lists: list[TrelloList], index_dir: Path) -> None:
    """Build list index."""
    from trache.cache.db import write_lists

    cache_dir = _cache_dir_from_index_dir(index_dir)
    write_lists(lists, cache_dir)


def load_index(index_dir: Path, name: str) -> dict:
    """Load a specific section of the index by name."""
    from trache.cache.db import load_cards_index, load_uid6_index, read_lists

    cache_dir = _cache_dir_from_index_dir(index_dir)

    if name == "cards_by_id":
        return load_cards_index(cache_dir)
    elif name == "cards_by_uid6":
        return load_uid6_index(cache_dir)
    elif name == "lists_by_id":
        return read_lists(cache_dir)
    elif name == "cards_by_list":
        # Build cards_by_list from cards index
        cards_index = load_cards_index(cache_dir)
        by_list: dict[str, list[str]] = {}
        for card_id, info in cards_index.items():
            by_list.setdefault(info["list_id"], []).append(card_id)
        return by_list
    return {}


def add_card_to_index(card: Card, index_dir: Path) -> None:
    """Add or update a single card in the index."""
    from trache.cache.db import write_card

    cache_dir = _cache_dir_from_index_dir(index_dir)
    write_card(card, "working", cache_dir)


def update_cards_in_index(cards: list[Card], index_dir: Path) -> None:
    """Add or update multiple cards in the index."""
    from trache.cache.db import write_cards_batch

    cache_dir = _cache_dir_from_index_dir(index_dir)
    write_cards_batch(cards, "working", cache_dir)


def remove_card_from_index(card_id: str, index_dir: Path) -> None:
    """Remove a card from the index."""
    from trache.cache.db import delete_card

    cache_dir = _cache_dir_from_index_dir(index_dir)
    delete_card(card_id, "working", cache_dir)


def add_list_to_index(list_id: str, name: str, pos: float, index_dir: Path) -> None:
    """Add a new list to the index."""
    from trache.cache.db import add_list

    cache_dir = _cache_dir_from_index_dir(index_dir)
    add_list(list_id, name, pos, cache_dir)


def update_list_in_index(list_id: str, name: str, pos: float, index_dir: Path) -> None:
    """Update an existing list in the index."""
    from trache.cache.db import update_list

    cache_dir = _cache_dir_from_index_dir(index_dir)
    update_list(list_id, name, pos, cache_dir)


def remove_list_from_index(list_id: str, index_dir: Path) -> None:
    """Remove a list from the index."""
    from trache.cache.db import remove_list

    cache_dir = _cache_dir_from_index_dir(index_dir)
    remove_list(list_id, cache_dir)


def resolve_card_id(identifier: str, index_dir: Path) -> str:
    """Resolve a card ID or UID6 to a full card ID."""
    from trache.cache.db import resolve_card_id as db_resolve

    cache_dir = _cache_dir_from_index_dir(index_dir)
    return db_resolve(identifier, cache_dir)


def resolve_list_id(identifier: str, index_dir: Path) -> str:
    """Resolve a list ID or name to a full list ID."""
    from trache.cache.db import resolve_list_id as db_resolve

    cache_dir = _cache_dir_from_index_dir(index_dir)
    return db_resolve(identifier, cache_dir)


def resolve_list_name(list_id: str, index_dir: Path) -> str:
    """Resolve a list ID to its human-readable name."""
    from trache.cache.db import resolve_list_name as db_resolve

    cache_dir = _cache_dir_from_index_dir(index_dir)
    return db_resolve(identifier=list_id, cache_dir=cache_dir)
