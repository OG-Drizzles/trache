"""Build and maintain JSON lookup indexes for fast discovery."""

from __future__ import annotations

import json
from pathlib import Path

from trache.cache.models import Card, TrelloList

INDEX_FILENAME = "index.json"

# Old separate index files (for migration cleanup)
_OLD_INDEX_FILES = [
    "cards_by_id.json", "cards_by_uid6.json",
    "cards_by_list.json", "lists_by_id.json",
]


def build_index(
    cards: list[Card], lists: list[TrelloList], index_dir: Path
) -> None:
    """Build the unified discovery index."""
    index_dir.mkdir(parents=True, exist_ok=True)

    index = {
        "cards_by_id": {},
        "cards_by_uid6": {},
        "cards_by_list": {},
        "lists_by_id": {},
    }

    for card in cards:
        index["cards_by_id"][card.id] = {
            "title": card.title,
            "list_id": card.list_id,
            "uid6": card.uid6,
            "modified_at": (
                card.content_modified_at.isoformat() if card.content_modified_at else None
            ),
        }
        index["cards_by_uid6"][card.uid6] = card.id
        index["cards_by_list"].setdefault(card.list_id, []).append(card.id)

    for lst in lists:
        index["lists_by_id"][lst.id] = {"name": lst.name, "pos": lst.pos}

    _write_json(index_dir / INDEX_FILENAME, index)

    # Clean up old separate files (migration)
    for old_file in _OLD_INDEX_FILES:
        old_path = index_dir / old_file
        if old_path.exists():
            old_path.unlink()


# Keep old entry points as aliases for backward compatibility during transition
def build_card_indexes(cards: list[Card], index_dir: Path) -> None:
    """Rebuild card sections of the unified index, preserving lists_by_id."""
    index_dir.mkdir(parents=True, exist_ok=True)
    index = _load_full_index(index_dir)

    # Rebuild card sections
    index["cards_by_id"] = {}
    index["cards_by_uid6"] = {}
    index["cards_by_list"] = {}

    for card in cards:
        index["cards_by_id"][card.id] = {
            "title": card.title,
            "list_id": card.list_id,
            "uid6": card.uid6,
            "modified_at": (
                card.content_modified_at.isoformat() if card.content_modified_at else None
            ),
        }
        index["cards_by_uid6"][card.uid6] = card.id
        index["cards_by_list"].setdefault(card.list_id, []).append(card.id)

    _write_json(index_dir / INDEX_FILENAME, index)

    # Clean up old separate files
    for old_file in _OLD_INDEX_FILES:
        old_path = index_dir / old_file
        if old_path.exists():
            old_path.unlink()


def build_list_index(lists: list[TrelloList], index_dir: Path) -> None:
    """Build list index. Updates lists section of unified index."""
    index_dir.mkdir(parents=True, exist_ok=True)
    index = _load_full_index(index_dir)
    index["lists_by_id"] = {
        lst.id: {"name": lst.name, "pos": lst.pos}
        for lst in lists
    }
    _write_json(index_dir / INDEX_FILENAME, index)

    # Clean up old file
    old_path = index_dir / "lists_by_id.json"
    if old_path.exists():
        old_path.unlink()


def _load_full_index(index_dir: Path) -> dict:
    """Load the full unified index, or initialize empty."""
    path = index_dir / INDEX_FILENAME
    if path.exists():
        return json.loads(path.read_text())

    # Try migrating from old separate files
    index: dict = {
        "cards_by_id": {},
        "cards_by_uid6": {},
        "cards_by_list": {},
        "lists_by_id": {},
    }
    for section in index:
        old_path = index_dir / f"{section}.json"
        if old_path.exists():
            index[section] = json.loads(old_path.read_text())
    return index


def load_index(index_dir: Path, name: str) -> dict:
    """Load a specific section of the index by name."""
    index = _load_full_index(index_dir)
    section = index.get(name, {})
    if section:
        return section

    # Fallback: try old separate file (backward compat on first run)
    old_path = index_dir / f"{name}.json"
    if old_path.exists():
        return json.loads(old_path.read_text())
    return {}


def add_card_to_index(card: Card, index_dir: Path) -> None:
    """Add or update a single card in the index."""
    index = _load_full_index(index_dir)
    index["cards_by_id"][card.id] = {
        "title": card.title,
        "list_id": card.list_id,
        "uid6": card.uid6,
        "modified_at": card.content_modified_at.isoformat() if card.content_modified_at else None,
    }
    index["cards_by_uid6"][card.uid6] = card.id
    index["cards_by_list"].setdefault(card.list_id, [])
    if card.id not in index["cards_by_list"][card.list_id]:
        index["cards_by_list"][card.list_id].append(card.id)
    _write_json(index_dir / INDEX_FILENAME, index)


def remove_card_from_index(card_id: str, index_dir: Path) -> None:
    """Remove a card from the index."""
    index = _load_full_index(index_dir)
    entry = index["cards_by_id"].pop(card_id, None)
    if entry:
        index["cards_by_uid6"].pop(entry.get("uid6", ""), None)
        for lst in index["cards_by_list"].values():
            if card_id in lst:
                lst.remove(card_id)
    _write_json(index_dir / INDEX_FILENAME, index)


def add_list_to_index(list_id: str, name: str, pos: float, index_dir: Path) -> None:
    """Add a new list to the index."""
    index = _load_full_index(index_dir)
    index["lists_by_id"][list_id] = {"name": name, "pos": pos}
    _write_json(index_dir / INDEX_FILENAME, index)


def update_list_in_index(list_id: str, name: str, pos: float, index_dir: Path) -> None:
    """Update an existing list in the index."""
    index = _load_full_index(index_dir)
    existing = index["lists_by_id"].get(list_id, {})
    index["lists_by_id"][list_id] = {"name": name, "pos": existing.get("pos", pos)}
    _write_json(index_dir / INDEX_FILENAME, index)


def remove_list_from_index(list_id: str, index_dir: Path) -> None:
    """Remove a list from the index."""
    index = _load_full_index(index_dir)
    index["lists_by_id"].pop(list_id, None)
    # Also remove from cards_by_list
    index["cards_by_list"].pop(list_id, None)
    _write_json(index_dir / INDEX_FILENAME, index)


def resolve_card_id(identifier: str, index_dir: Path) -> str:
    """Resolve a card ID or UID6 to a full card ID.

    Raises KeyError with a specific message depending on failure reason:
    - No board initialised (no index file)
    - Invalid UID6 format
    - Card not found on this board
    """
    # Check board is initialised
    index_path = index_dir / INDEX_FILENAME
    has_index = index_path.exists()
    if not has_index and not index_dir.exists():
        raise KeyError(
            f"No board initialised. Run 'trache init' and 'trache pull' first."
        )

    # If it looks like a full ID (24 hex chars), return as-is
    if len(identifier) == 24:
        return identifier

    # Validate UID6 format: 1-6 hex characters (or temp IDs containing '_' or '~')
    is_temp_id = "_" in identifier or "~" in identifier
    if not is_temp_id:
        upper_id = identifier.upper()
        if not (1 <= len(identifier) <= 6 and all(c in "0123456789ABCDEF" for c in upper_id)):
            raise KeyError(
                f"Invalid card identifier format: '{identifier}'. "
                f"Expected a 6-character hex UID6 (e.g. 'A1B2C3'), "
                f"a 24-character full card ID, or a temp ID."
            )
    else:
        upper_id = identifier.upper()

    # Try UID6 lookup
    uid6_index = load_index(index_dir, "cards_by_uid6")
    if upper_id in uid6_index:
        return uid6_index[upper_id]

    # Also try temp card IDs (e.g., "new_abc123...")
    cards_by_id = load_index(index_dir, "cards_by_id")
    if identifier in cards_by_id:
        return identifier

    # Safety net: scan working directory for unindexed cards
    working_dir = index_dir.parent / "working" / "cards"
    if working_dir.exists():
        for card_file in working_dir.glob("*.md"):
            stem = card_file.stem
            if stem == identifier or stem[-6:].upper() == upper_id:
                return stem

    raise KeyError(
        f"Card '{identifier}' not found on this board. "
        f"Run 'trache card list' to see available cards, "
        f"or 'trache pull' to refresh from Trello."
    )


def resolve_list_id(identifier: str, index_dir: Path) -> str:
    """Resolve a list ID or name to a full list ID."""
    # If it looks like a full ID (24 hex chars), return as-is
    if len(identifier) == 24:
        return identifier

    # Try name lookup — collect all matches to detect ambiguity
    lists_index = load_index(index_dir, "lists_by_id")
    matches: list[tuple[str, str]] = []  # (list_id, name)
    for list_id, info in lists_index.items():
        if info["name"].lower() == identifier.lower():
            matches.append((list_id, info["name"]))

    if len(matches) == 1:
        return matches[0][0]
    if len(matches) > 1:
        ids = ", ".join(f"{name} ({lid})" for lid, name in matches)
        raise KeyError(
            f"Ambiguous list name '{identifier}': matches {len(matches)} lists: {ids}. "
            f"Use the full list ID instead."
        )

    raise KeyError(f"Cannot resolve list identifier: {identifier}")


def resolve_list_name(list_id: str, index_dir: Path) -> str:
    """Resolve a list ID to its human-readable name. Falls back to raw ID."""
    lists_index = load_index(index_dir, "lists_by_id")
    info = lists_index.get(list_id)
    if info:
        return info["name"]
    return list_id


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
