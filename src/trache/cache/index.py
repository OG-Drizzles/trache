"""Build and maintain JSON lookup indexes for fast discovery."""

from __future__ import annotations

import json
from pathlib import Path

from trache.cache.models import Card, TrelloList


def build_card_indexes(cards: list[Card], index_dir: Path) -> None:
    """Build all card indexes from a list of cards."""
    index_dir.mkdir(parents=True, exist_ok=True)

    cards_by_id: dict[str, dict] = {}
    cards_by_uid6: dict[str, str] = {}
    cards_by_list: dict[str, list[str]] = {}

    for card in cards:
        cards_by_id[card.id] = {
            "title": card.title,
            "list_id": card.list_id,
            "uid6": card.uid6,
            "modified_at": (
                card.content_modified_at.isoformat() if card.content_modified_at else None
            ),
        }
        cards_by_uid6[card.uid6] = card.id
        cards_by_list.setdefault(card.list_id, []).append(card.id)

    _write_json(index_dir / "cards_by_id.json", cards_by_id)
    _write_json(index_dir / "cards_by_uid6.json", cards_by_uid6)
    _write_json(index_dir / "cards_by_list.json", cards_by_list)


def build_list_index(lists: list[TrelloList], index_dir: Path) -> None:
    """Build list index."""
    index_dir.mkdir(parents=True, exist_ok=True)
    lists_by_id = {
        lst.id: {"name": lst.name, "pos": lst.pos}
        for lst in lists
    }
    _write_json(index_dir / "lists_by_id.json", lists_by_id)


def load_index(index_dir: Path, name: str) -> dict:
    """Load a JSON index file by name."""
    path = index_dir / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def resolve_card_id(identifier: str, index_dir: Path) -> str:
    """Resolve a card ID or UID6 to a full card ID."""
    # If it looks like a full ID (24 hex chars), return as-is
    if len(identifier) == 24:
        return identifier

    # Try UID6 lookup
    uid6_index = load_index(index_dir, "cards_by_uid6")
    upper_id = identifier.upper()
    if upper_id in uid6_index:
        return uid6_index[upper_id]

    # Try case-insensitive UID6
    for uid6, card_id in uid6_index.items():
        if uid6.upper() == upper_id:
            return card_id

    raise KeyError(f"Cannot resolve card identifier: {identifier}")


def resolve_list_id(identifier: str, index_dir: Path) -> str:
    """Resolve a list ID or name to a full list ID."""
    # If it looks like a full ID (24 hex chars), return as-is
    if len(identifier) == 24:
        return identifier

    # Try name lookup
    lists_index = load_index(index_dir, "lists_by_id")
    for list_id, info in lists_index.items():
        if info["name"].lower() == identifier.lower():
            return list_id

    raise KeyError(f"Cannot resolve list identifier: {identifier}")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
