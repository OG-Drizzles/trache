"""Clean snapshot management — baseline after pull."""

from __future__ import annotations

from pathlib import Path

from trache.cache.models import Card
from trache.cache.store import list_card_files, read_card_file, write_card_file


def write_clean_snapshot(cards: list[Card], cache_dir: Path) -> None:
    """Write all cards to the clean snapshot directory.

    This overwrites the entire clean directory — called only during pull.
    """
    clean_dir = cache_dir / "clean" / "cards"
    clean_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing card files not in the new set
    existing_ids = {p.stem for p in list_card_files(clean_dir)}
    new_ids = {c.id for c in cards}
    for stale_id in existing_ids - new_ids:
        (clean_dir / f"{stale_id}.md").unlink(missing_ok=True)

    for card in cards:
        write_card_file(card, clean_dir)


def read_clean_card(card_id: str, cache_dir: Path) -> Card:
    """Read a single card from the clean snapshot."""
    path = cache_dir / "clean" / "cards" / f"{card_id}.md"
    return read_card_file(path)


def list_clean_cards(cache_dir: Path) -> list[Card]:
    """Read all cards from the clean snapshot."""
    clean_dir = cache_dir / "clean" / "cards"
    return [read_card_file(p) for p in list_card_files(clean_dir)]
