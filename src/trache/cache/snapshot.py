"""Clean snapshot management — baseline after pull."""

from __future__ import annotations

from pathlib import Path

from trache.cache.db import (
    delete_stale_cards,
    list_cards,
    read_card,
    write_cards_batch,
)
from trache.cache.models import Card


def write_clean_snapshot(cards: list[Card], cache_dir: Path) -> None:
    """Write all cards to the clean snapshot, removing stale entries."""
    new_ids = {c.id for c in cards}
    delete_stale_cards(new_ids, "clean", cache_dir)
    write_cards_batch(cards, "clean", cache_dir)


def read_clean_card(card_id: str, cache_dir: Path) -> Card:
    """Read a single card from the clean snapshot."""
    return read_card(card_id, "clean", cache_dir)


def list_clean_cards(cache_dir: Path) -> list[Card]:
    """Read all cards from the clean snapshot."""
    return list_cards("clean", cache_dir)
